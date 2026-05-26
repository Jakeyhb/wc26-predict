import type { ReactNode } from "react";
import { Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { BarChart3, CalendarClock, FileText, MessageSquareMore, ShieldCheck } from "lucide-react";
import { HomePage } from "./pages/HomePage";
import { MatchPage } from "./pages/MatchPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SchedulePage } from "./pages/SchedulePage";
import { StatsPage } from "./pages/StatsPage";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { AdminSignalsPage } from "./pages/AdminSignalsPage";
import { AdminArticlesPage } from "./pages/AdminArticlesPage";
import { AdminFeedbackPage } from "./pages/AdminFeedbackPage";
import { AdminMatchesPage } from "./pages/AdminMatchesPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { AdminTokenGate } from "./components/AdminTokenGate";

export default function App() {
  return (
    <div className="min-h-screen px-4 pb-16 pt-6">
      <header className="content-wrap mb-6 rounded-[30px] border border-white/8 bg-black/20 px-5 py-4 backdrop-blur">
        <div className="flex items-center justify-between gap-4">
          <Link to="/" className="font-display text-2xl">
            WC26 Predict
          </Link>
          <nav className="flex items-center gap-2 text-sm text-text-secondary">
            <TopNavLink to="/" label="首页" />
            <TopNavLink to="/schedule" label="赛程" />
            <TopNavLink to="/stats" label="准确率" />
            <TopNavLink to="/admin/dashboard" label="后台" />
          </nav>
        </div>
      </header>

      <main className="content-wrap">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/match/:matchId" element={<MatchPage />} />
          <Route path="/match/:matchId/review" element={<ReviewPage />} />
          <Route
            path="/admin/*"
            element={
              <AdminTokenGate>
                {(token) => (
                  <div className="space-y-5">
                    <div className="flex gap-2 overflow-x-auto rounded-[24px] border border-white/8 bg-black/20 p-2">
                      <AdminNav to="/admin/dashboard" icon={<BarChart3 className="h-4 w-4" />} label="Dashboard" />
                      <AdminNav to="/admin/signals" icon={<ShieldCheck className="h-4 w-4" />} label="Signals" />
                      <AdminNav to="/admin/articles" icon={<FileText className="h-4 w-4" />} label="Articles" />
                      <AdminNav to="/admin/matches" icon={<CalendarClock className="h-4 w-4" />} label="Matches" />
                      <AdminNav to="/admin/feedback" icon={<MessageSquareMore className="h-4 w-4" />} label="Feedback" />
                    </div>
                    <Routes>
                      <Route index element={<Navigate to="dashboard" replace />} />
                      <Route path="dashboard" element={<AdminDashboardPage token={token} />} />
                      <Route path="signals" element={<AdminSignalsPage token={token} />} />
                      <Route path="articles" element={<AdminArticlesPage token={token} />} />
                      <Route path="matches" element={<AdminMatchesPage token={token} />} />
                      <Route path="feedback" element={<AdminFeedbackPage token={token} />} />
                      <Route path="*" element={<NotFoundPage />} />
                    </Routes>
                  </div>
                )}
              </AdminTokenGate>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}

function TopNavLink({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-full px-3 py-2 transition ${isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"}`
      }
    >
      {label}
    </NavLink>
  );
}

function AdminNav({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-full px-4 py-2 text-sm transition ${
          isActive ? "bg-white/10 text-white" : "text-text-secondary hover:bg-white/5 hover:text-white"
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}
