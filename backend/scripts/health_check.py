from __future__ import annotations

import asyncio
import argparse
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
import os
from pathlib import Path
import subprocess
import shutil
import sys
from typing import Awaitable, Callable

import httpx
from redis import Redis
from sqlalchemy import func, select, text

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.models import Match, PostmatchEval, PredictionRun
from app.services.calibration import IsotonicCalibrator
from app.services.dixon_coles import DixonColesModel, load_training_frame, WC26_FIFA_TIERS
from app.services.embedding_service import EmbeddingService
from app.services.football_data_service import FootballDataService
from app.services.llm_service import get_llm_adapter
from app.services.news_ingest_service import NewsIngestService
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.workers.celery_app import celery_app

settings = get_settings()


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


async def check_postgres() -> CheckResult:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return CheckResult("PostgreSQL连接正常", True, "数据库查询成功")
    except Exception as exc:
        return CheckResult("PostgreSQL连接正常", False, str(exc))


async def check_redis() -> CheckResult:
    try:
        redis = Redis.from_url(settings.redis_url)
        redis.ping()
        return CheckResult("Redis连接正常", True, "PING 成功")
    except Exception as exc:
        return CheckResult("Redis连接正常", False, str(exc))


async def check_football_data() -> CheckResult:
    if not settings.football_data_api_key:
        return CheckResult("football-data.org API可访问", False, "未配置 FOOTBALL_DATA_API_KEY")
    try:
        matches = await FootballDataService().fetch_competition_matches("PL", 2024, status="FINISHED")
        ok = len(matches) > 0
        return CheckResult("football-data.org API可访问", ok, f"PL 2024 返回 {len(matches)} 场比赛")
    except Exception as exc:
        return CheckResult("football-data.org API可访问", False, str(exc))


async def check_historical_data() -> CheckResult:
    try:
        async with AsyncSessionLocal() as db:
            count = await db.scalar(select(func.count()).select_from(Match)) or 0
        return CheckResult("历史比赛数据已加载", count > 0, f"matches={count}")
    except Exception as exc:
        return CheckResult("历史比赛数据已加载", False, str(exc))


async def _fit_model() -> tuple[DixonColesModel, object, TabularMatchEnhancer, object, int, object]:
    async with AsyncSessionLocal() as db:
        matches_df = await load_training_frame(db, competition_type="national", team_type="national")
    # Build team_info from all available teams
    team_info = {}
    for team_name in set(matches_df["home_team"]).union(matches_df["away_team"]):
        team_info[team_name] = {"confederation": "FIFA", "fifa_tier": WC26_FIFA_TIERS.get(team_name, 0)}
    model = DixonColesModel()
    model.set_team_info(team_info)
    fit_summary = model.fit(matches_df)
    enhancer = TabularMatchEnhancer()
    enhancer_summary = enhancer.fit(matches_df)
    return model, fit_summary, enhancer, enhancer_summary, len(matches_df), matches_df


async def check_model_train() -> CheckResult:
    try:
        _, fit_summary, enhancer, enhancer_summary, rows, _ = await _fit_model()
        return CheckResult(
            "预测模型栈可以训练",
            bool(getattr(fit_summary, "converged", False)) and enhancer.is_fitted,
            (
                f"rows={rows}, dc_converged={fit_summary.converged}, dc_loss={fit_summary.final_neg_log_likelihood:.6f}, "
                f"tabular_rows={enhancer_summary.training_rows}"
            ),
        )
    except Exception as exc:
        return CheckResult("预测模型栈可以训练", False, str(exc))


async def check_model_predict() -> CheckResult:
    try:
        model, _, enhancer, _, _, training_df = await _fit_model()
        prediction = model.predict_match("Brazil", "France", is_neutral_venue=True)
        enhancer_prediction = enhancer.predict_match(
            home_team="Brazil",
            away_team="France",
            match_date=datetime.now(UTC),
            competition_weight=1.0,
            is_neutral_venue=True,
            training_df=training_df,
            rest_days={"home": 5, "away": 5},
        )
        fused = fuse_outcome_probabilities(
            {
                "home_win_prob": float(prediction["home_win_prob"]),
                "draw_prob": float(prediction["draw_prob"]),
                "away_win_prob": float(prediction["away_win_prob"]),
            },
            {
                "home_win_prob": float(enhancer_prediction["home_win_prob"]),
                "draw_prob": float(enhancer_prediction["draw_prob"]),
                "away_win_prob": float(enhancer_prediction["away_win_prob"]),
            },
            base_weight=0.68,
        )
        return CheckResult(
            "两支已知球队可以生成融合预测结果",
            True,
            f"home={fused['home_win_prob']:.3f} draw={fused['draw_prob']:.3f} away={fused['away_win_prob']:.3f}",
        )
    except Exception as exc:
        return CheckResult("两支已知球队可以生成融合预测结果", False, str(exc))


async def check_llm_api() -> CheckResult:
    if not settings.llm_api_key:
        return CheckResult("LLM API可访问", False, "未配置 LLM_API_KEY")
    try:
        adapter = get_llm_adapter()
        response = await adapter.chat("You are a health check.", "Reply with OK.", response_format="text")
        return CheckResult("LLM API可访问", bool(response.strip()), response.strip()[:60])
    except Exception as exc:
        return CheckResult("LLM API可访问", False, str(exc))


async def check_news_api() -> CheckResult:
    try:
        service = NewsIngestService()
        articles = await service.fetch_gdelt(hours_back=1)
        return CheckResult("新闻采集API可访问", len(articles) >= 0, f"GDELT 返回 {len(articles)} 条")
    except Exception as exc:
        if "429" in str(exc):
            return CheckResult("新闻采集API可访问", True, "GDELT 当前限流，但接口可达")
        return CheckResult("新闻采集API可访问", False, str(exc))


async def check_fastapi() -> CheckResult:
    base_url = _resolve_app_base_url()
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            health = await client.get("/health")
            upcoming = await client.get("/api/matches/upcoming")
            schedule = await client.get("/api/matches/schedule")
            dashboard = await client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {settings.admin_token}"})

            if not all(response.status_code == 200 for response in (health, upcoming, schedule, dashboard)):
                return CheckResult(
                    "FastAPI所有核心接口返回200",
                    False,
                    f"/health={health.status_code} upcoming={upcoming.status_code} schedule={schedule.status_code} dashboard={dashboard.status_code}",
                )

            async with AsyncSessionLocal() as db:
                prediction_run = await db.scalar(select(PredictionRun).order_by(PredictionRun.created_at.desc()).limit(1))
                review_eval = await db.scalar(select(PostmatchEval).order_by(PostmatchEval.created_at.desc()).limit(1))
                review_run = None
                if review_eval is not None:
                    review_run = await db.scalar(
                        select(PredictionRun)
                        .where(PredictionRun.id == review_eval.prediction_run_id)
                        .limit(1)
                    )

            if prediction_run is not None:
                latest = await client.get(f"/api/predictions/{prediction_run.match_id}/latest")
                history = await client.get(f"/api/predictions/{prediction_run.match_id}/history")
                evidence = await client.get(f"/api/matches/{prediction_run.match_id}/evidence")
                if latest.status_code != 200 or history.status_code != 200 or evidence.status_code != 200:
                    return CheckResult(
                        "FastAPI所有核心接口返回200",
                        False,
                        f"latest={latest.status_code} history={history.status_code} evidence={evidence.status_code}",
                    )
            if review_run is not None:
                review = await client.get(f"/api/matches/{review_run.match_id}/review")
                if review.status_code != 200:
                    return CheckResult("FastAPI所有核心接口返回200", False, f"review={review.status_code}")
            return CheckResult("FastAPI所有核心接口返回200", True, "health/upcoming/schedule/dashboard/latest/history/review 可用")
    except Exception as exc:
        return CheckResult("FastAPI所有核心接口返回200", False, str(exc))


async def check_celery() -> CheckResult:
    try:
        replies = celery_app.control.ping(timeout=2)
        return CheckResult("Celery worker可以接收任务", bool(replies), f"replies={replies}")
    except Exception as exc:
        return CheckResult("Celery worker可以接收任务", False, str(exc))


async def check_frontend_build() -> CheckResult:
    try:
        npm_command = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm_command:
            return CheckResult("前端build成功", False, "未找到 npm")
        completed = await asyncio.to_thread(
            subprocess.run,
            [npm_command, "run", "build"],
            cwd=ROOT_DIR / "apps" / "web",
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-5:]
            return CheckResult("前端build成功", False, " | ".join(detail))
        return CheckResult("前端build成功", True, "npm run build 通过")
    except Exception as exc:
        return CheckResult("前端build成功", False, str(exc))


async def check_schedule_seed() -> CheckResult:
    try:
        async with AsyncSessionLocal() as db:
            count = await db.scalar(
                select(func.count()).select_from(Match).where(Match.competition.ilike("%2026%"))
            ) or 0
        return CheckResult("2026赛程数据已加载", count > 0, f"matches_2026={count}")
    except Exception as exc:
        return CheckResult("2026赛程数据已加载", False, str(exc))


async def check_calibrator_service() -> CheckResult:
    try:
        calibrator = IsotonicCalibrator()
        calibrator_path = settings.model_artifact_dir / "calibrator.json"
        if calibrator_path.exists():
            calibrator.load(str(calibrator_path))
        stats = calibrator.calibration_stats()
        return CheckResult(
            "IsotonicCalibrator可用",
            True,
            f"is_fitted={stats['is_fitted']} samples={stats['training_samples']}",
        )
    except Exception as exc:
        return CheckResult("IsotonicCalibrator可用", False, str(exc))


async def check_embedding_service() -> CheckResult:
    try:
        vector = await EmbeddingService().embed_text("test")
        return CheckResult("EmbeddingService可用", len(vector) > 0, f"dimensions={len(vector)}")
    except Exception as exc:
        return CheckResult("EmbeddingService可用", False, str(exc))


async def check_league_data_loaded() -> CheckResult:
    try:
        async with AsyncSessionLocal() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(Match)
                .where(text("competition_type = 'club'"))
            ) or 0
        return CheckResult(
            "五大联赛数据已加载",
            count > 0,
            f"联赛比赛数: {count} 场" if count > 0 else "联赛数据为空，请运行 init_data.py",
        )
    except Exception as exc:
        return CheckResult("五大联赛数据已加载", False, str(exc))


async def check_model_artifacts_by_type() -> CheckResult:
    try:
        artifact_dir = settings.model_artifact_dir
        club_files = list(artifact_dir.glob("club_*.json"))
        cup_files = list(artifact_dir.glob("cup_*.json"))
        national_files = list(artifact_dir.glob("national_*.json"))
        ok = bool(club_files and national_files)
        detail = f"club={len(club_files)} cup={len(cup_files)} national={len(national_files)}"
        return CheckResult("模型按类型分开存储", ok, detail)
    except Exception as exc:
        return CheckResult("模型按类型分开存储", False, str(exc))


async def check_celery_beat_task_count() -> CheckResult:
    schedule = celery_app.conf.beat_schedule or {}
    expected_tasks = {
        "app.workers.tasks.sync_matches_task",
        "app.workers.tasks.news_ingest_task",
        "app.workers.tasks.prediction_trigger_task",
        "app.workers.tasks.postmatch_eval_task",
        "app.workers.tasks.retrain_calibrator_task",
        "app.workers.tasks.embed_articles_task",
        "app.workers.tasks.sync_league_upcoming_task",
    }
    actual_tasks = {entry.get("task") for entry in schedule.values()}
    missing = expected_tasks - actual_tasks
    unexpected = actual_tasks - expected_tasks
    ok = not missing and len(actual_tasks) == len(expected_tasks)
    detail = f"configured={len(actual_tasks)} missing={sorted(missing)} unexpected={sorted(unexpected)}"
    return CheckResult("Celery Beat任务数量", ok, detail if not ok else f"configured={len(actual_tasks)}")


async def main(stage: int) -> None:
    configure_logging()
    stage_one_checks: list[Callable[[], Awaitable[CheckResult]]] = [
        check_postgres,
        check_redis,
        check_football_data,
        check_historical_data,
        check_model_train,
        check_model_predict,
        check_llm_api,
        check_news_api,
        check_fastapi,
        check_celery,
        check_frontend_build,
        check_schedule_seed,
        check_calibrator_service,
        check_embedding_service,
    ]
    stage_two_checks = [
        check_league_data_loaded,
        check_model_artifacts_by_type,
        check_celery_beat_task_count,
    ]
    checks = stage_one_checks if stage == 1 else [*stage_one_checks, *stage_two_checks]

    results: list[CheckResult] = []
    for check in checks:
        result = await check()
        results.append(result)
        print(f"{'✓' if result.ok else '✗'} {result.name} - {result.detail}")

    passed = sum(1 for result in results if result.ok)
    print(f"\n通过 {passed}/{len(checks)} 项检查")
    required = len(checks)
    if passed < required:
        failed = [result.name for result in results if not result.ok]
        print("需要修复：")
        for name in failed:
            print(f"- {name}")


def _resolve_app_base_url() -> str:
    configured = os.getenv("APP_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return settings.app_base_url.rstrip("/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WC26 health check")
    parser.add_argument("--stage", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    asyncio.run(main(args.stage))
