"""WC 2026 48-team squad data — complete player lists from FIFA official squads.

Source: KhelNow.com (June 2, 2026)

Data structure:
    SQUADS = {
        "Team Name in DB": {
            "players": [
                ("Player Name", "Position", is_key_player, importance_level),
                ...
            ]
        }
    }

Positions: GK=Goalkeeper, DF=Defence, MF=Midfield, FW=Forward
importance_level: starter (known star), squad, unknown
"""
# flake8: noqa: E501

SQUADS: dict[str, dict] = {}

# ═══════════════════════════════════════════════════════════
# Group A
# ═══════════════════════════════════════════════════════════

SQUADS["Mexico"] = {
    "players": [
        ("Carlos Acevedo", "GK", False, "squad"),
        ("Guillermo Ochoa", "GK", True, "starter"),
        ("Raúl Rangel", "GK", False, "squad"),
        ("Jesús Gallardo", "DF", False, "squad"),
        ("Israel Reyes", "DF", False, "squad"),
        ("César Montes", "DF", True, "starter"),
        ("Jorge Sánchez", "DF", False, "squad"),
        ("Johan Vásquez", "DF", False, "squad"),
        ("Mateo Chávez", "DF", False, "squad"),
        ("Gilberto Mora", "MF", False, "squad"),
        ("Edson Álvarez", "MF", True, "starter"),
        ("Orbelín Pineda", "MF", False, "squad"),
        ("Luis Romo", "MF", False, "squad"),
        ("Brian Gutiérrez", "MF", False, "squad"),
        ("Obed Vargas", "MF", False, "squad"),
        ("César Huerta", "MF", False, "squad"),
        ("Luis Chávez", "MF", False, "squad"),
        ("Erik Lira", "MF", False, "squad"),
        ("Álvaro Fidalgo", "MF", False, "squad"),
        ("Roberto Alvarado", "MF", False, "squad"),
        ("Armando González", "FW", False, "squad"),
        ("Raúl Jiménez", "FW", True, "starter"),
        ("Julián Quiñones", "FW", False, "squad"),
        ("Santiago Giménez", "FW", True, "starter"),
        ("Guillermo Martínez", "FW", False, "squad"),
        ("Alexis Vega", "FW", False, "squad"),
    ]
}

SQUADS["South Africa"] = {
    "players": [
        ("Ronwen Williams", "GK", True, "starter"),
        ("Ricardo Goss", "GK", False, "squad"),
        ("Sipho Chaine", "GK", False, "squad"),
        ("Khuliso Mudau", "DF", False, "squad"),
        ("Nkosinathi Sibisi", "DF", False, "squad"),
        ("Ime Okon", "DF", False, "squad"),
        ("Khulumani Ndamane", "DF", False, "squad"),
        ("Aubrey Modiba", "DF", False, "squad"),
        ("Samukelo Kabini", "DF", False, "squad"),
        ("Thabang Matuludi", "DF", False, "squad"),
        ("Olwethu Makhanya", "DF", False, "squad"),
        ("Kamgogelo Sebelebele", "DF", False, "squad"),
        ("Bradley Cross", "DF", False, "squad"),
        ("Mbekezeli Mbokazi", "DF", False, "squad"),
        ("Teboho Mokoena", "MF", True, "starter"),
        ("Thalente Mbatha", "MF", False, "squad"),
        ("Yaya Sithole", "MF", False, "squad"),
        ("Jayden Adams", "MF", False, "squad"),
        ("Oswin Appollis", "FW", False, "squad"),
        ("Iqraam Rayners", "FW", False, "squad"),
        ("Tshepang Moremi", "FW", False, "squad"),
        ("Relebohile Mofokeng", "FW", False, "squad"),
        ("Evidence Makgopa", "FW", False, "squad"),
        ("Themba Zwane", "FW", False, "squad"),
        ("Lyle Foster", "FW", True, "starter"),
        ("Thapelo Maseko", "FW", False, "squad"),
    ]
}

SQUADS["South Korea"] = {
    "players": [
        ("Jo Hyun-Woo", "GK", False, "squad"),
        ("Kim Seung-Gyu", "GK", True, "starter"),
        ("Song Bum-Keun", "GK", False, "squad"),
        ("Kim Min-Jae", "DF", True, "starter"),
        ("Jo Yu-Min", "DF", False, "squad"),
        ("Lee Han-Beom", "DF", False, "squad"),
        ("Kim Tae-Hyun", "DF", False, "squad"),
        ("Park Jin-Seop", "DF", False, "squad"),
        ("Lee Ki-Hyeok", "DF", False, "squad"),
        ("Lee Tae-Seok", "DF", False, "squad"),
        ("Seol Young-Woo", "DF", False, "squad"),
        ("Jens Castrop", "DF", False, "squad"),
        ("Kim Moon-Hwan", "DF", False, "squad"),
        ("Yang Hyun-Jun", "MF", False, "squad"),
        ("Paik Seung-Ho", "MF", False, "squad"),
        ("Hwang In-Beom", "MF", True, "starter"),
        ("Kim Jin-Kyu", "MF", False, "squad"),
        ("Bae Jun-Ho", "MF", False, "squad"),
        ("Um Ji-Sung", "MF", False, "squad"),
        ("Hwang Hee-Chan", "MF", True, "starter"),
        ("Lee Dong-Gyeong", "MF", False, "squad"),
        ("Lee Jae-Sung", "MF", False, "squad"),
        ("Lee Kang-In", "MF", True, "starter"),
        ("Oh Hyun-Kyu", "FW", False, "squad"),
        ("Son Heung-Min", "FW", True, "starter"),
        ("Cho Kyu-Sung", "FW", False, "squad"),
    ]
}

SQUADS["Czech Republic"] = {
    "players": [
        ("Lukáš Horníček", "GK", False, "squad"),
        ("Matěj Kovář", "GK", True, "starter"),
        ("Jindřich Staněk", "GK", False, "squad"),
        ("Vladimír Coufal", "DF", True, "starter"),
        ("David Doudera", "DF", False, "squad"),
        ("Tomáš Holeš", "DF", False, "squad"),
        ("Robin Hranáč", "DF", False, "squad"),
        ("Štěpán Chaloupek", "DF", False, "squad"),
        ("David Jurásek", "DF", False, "squad"),
        ("Ladislav Krejčí", "DF", False, "squad"),
        ("Jaroslav Zelený", "DF", False, "squad"),
        ("David Zima", "DF", False, "squad"),
        ("Lukáš Červ", "MF", False, "squad"),
        ("Vladimír Darida", "MF", False, "squad"),
        ("Lukáš Provod", "MF", False, "squad"),
        ("Michal Sadílek", "MF", False, "squad"),
        ("Hugo Sochůrek", "MF", False, "squad"),
        ("Alexandr Sojka", "MF", False, "squad"),
        ("Tomáš Souček", "MF", True, "starter"),
        ("Pavel Šulc", "MF", False, "squad"),
        ("Denis Višinský", "MF", False, "squad"),
        ("Tomáš Chorý", "FW", False, "squad"),
        ("Adam Hložek", "FW", False, "squad"),
        ("Mojmír Chytil", "FW", False, "squad"),
        ("Jan Kuchta", "FW", False, "squad"),
        ("Patrik Schick", "FW", True, "starter"),
    ]
}

# ═══════════════════════════════════════════════════════════
# Group B
# ═══════════════════════════════════════════════════════════

SQUADS["Canada"] = {
    "players": [
        ("Dayne St. Clair", "GK", False, "squad"),
        ("Maxime Crépeau", "GK", True, "starter"),
        ("Owen Goodman", "GK", False, "squad"),
        ("Moïse Bombito", "DF", False, "squad"),
        ("Derek Cornelius", "DF", False, "squad"),
        ("Alphonso Davies", "DF", True, "starter"),
        ("Luc De Fougerolles", "DF", False, "squad"),
        ("Alistair Johnston", "DF", True, "starter"),
        ("Alfie Jones", "DF", False, "squad"),
        ("Richie Laryea", "DF", False, "squad"),
        ("Niko Sigur", "DF", False, "squad"),
        ("Joel Waterman", "DF", False, "squad"),
        ("Ali Ahmed", "MF", False, "squad"),
        ("Tajon Buchanan", "MF", True, "starter"),
        ("Mathieu Choinière", "MF", False, "squad"),
        ("Stephen Eustáquio", "MF", True, "starter"),
        ("Marcelo Flores", "MF", False, "squad"),
        ("Ismaël Koné", "MF", False, "squad"),
        ("Liam Millar", "MF", False, "squad"),
        ("Jonathan Osorio", "MF", False, "squad"),
        ("Nathan Saliba", "MF", False, "squad"),
        ("Jacob Shaffelburg", "MF", False, "squad"),
        ("Jonathan David", "FW", True, "starter"),
        ("Promise David", "FW", False, "squad"),
        ("Cyle Larin", "FW", True, "starter"),
        ("Tani Oluwaseyi", "FW", False, "squad"),
    ]
}

SQUADS["Bosnia and Herzegovina"] = {
    "players": [
        ("Nikola Vasilj", "GK", True, "starter"),
        ("Martin Zlomislić", "GK", False, "squad"),
        ("Osman Hadžikić", "GK", False, "squad"),
        ("Sead Kolašinac", "DF", True, "starter"),
        ("Amar Dedić", "DF", False, "squad"),
        ("Nihad Mujakić", "DF", False, "squad"),
        ("Nikola Katić", "DF", False, "squad"),
        ("Tarik Muharemović", "DF", False, "squad"),
        ("Stjepan Radeljić", "DF", False, "squad"),
        ("Dennis Hadžikadunić", "DF", False, "squad"),
        ("Nidal Čelik", "DF", False, "squad"),
        ("Amir Hadžiahmetović", "MF", False, "squad"),
        ("Ivan Šunjić", "MF", False, "squad"),
        ("Ivan Bašić", "MF", False, "squad"),
        ("Dženis Burnić", "MF", False, "squad"),
        ("Ermin Mahmić", "MF", False, "squad"),
        ("Benjamin Tahirović", "MF", False, "squad"),
        ("Amar Memić", "MF", False, "squad"),
        ("Armin Gigović", "MF", False, "squad"),
        ("Kerim Alajbegović", "MF", False, "squad"),
        ("Esmir Bajraktarević", "MF", False, "squad"),
        ("Ermedin Demirović", "FW", True, "starter"),
        ("Jovo Lukić", "FW", False, "squad"),
        ("Samed Bazdar", "FW", False, "squad"),
        ("Haris Tabaković", "FW", False, "squad"),
        ("Edin Džeko", "FW", True, "starter"),
    ]
}

SQUADS["Qatar"] = {
    "players": [
        ("Salah Zakaria", "GK", True, "starter"),
        ("Meshaal Barsham", "GK", False, "squad"),
        ("Mahmoud Abunada", "GK", False, "squad"),
        ("Boualem Khoukhi", "DF", False, "squad"),
        ("Pedro Miguel", "DF", False, "squad"),
        ("Sultan Al Brake", "DF", False, "squad"),
        ("Al-Hashmi Al-Hussain", "DF", False, "squad"),
        ("Ayoub Al-Alawi", "DF", False, "squad"),
        ("Issa Laye", "DF", False, "squad"),
        ("Lucas Mendes", "DF", False, "squad"),
        ("Homam Al-Amin", "DF", False, "squad"),
        ("Ahmed Fathi", "MF", False, "squad"),
        ("Jassim Gaber", "MF", False, "squad"),
        ("Assim Madibo", "MF", False, "squad"),
        ("Abdulaziz Hatem", "MF", False, "squad"),
        ("Karim Boudiaf", "MF", False, "squad"),
        ("Mohammed Mannai", "MF", False, "squad"),
        ("Almoez Ali", "FW", True, "starter"),
        ("Akram Afif", "FW", True, "starter"),
        ("Tahsin Mohammed", "FW", False, "squad"),
        ("Edmílson Junior", "FW", False, "squad"),
        ("Ahmed Al-Ganehi", "FW", False, "squad"),
        ("Ahmed Alaa", "FW", False, "squad"),
        ("Hassan Al-Haydos", "FW", True, "starter"),
        ("Mohammed Muntari", "FW", False, "squad"),
        ("Yusuf Abdurisag", "FW", False, "squad"),
    ]
}

SQUADS["Switzerland"] = {
    "players": [
        ("Gregor Kobel", "GK", True, "starter"),
        ("Yvon Mvogo", "GK", False, "squad"),
        ("Marvin Keller", "GK", False, "squad"),
        ("Manuel Akanji", "DF", True, "starter"),
        ("Nico Elvedi", "DF", False, "squad"),
        ("Ricardo Rodriguez", "DF", True, "starter"),
        ("Silvan Widmer", "DF", False, "squad"),
        ("Miro Muheim", "DF", False, "squad"),
        ("Aurèle Amenda", "DF", False, "squad"),
        ("Eray Cömert", "DF", False, "squad"),
        ("Luca Jaquez", "DF", False, "squad"),
        ("Granit Xhaka", "MF", True, "starter"),
        ("Johan Manzambi", "MF", False, "squad"),
        ("Remo Freuler", "MF", False, "squad"),
        ("Denis Zakaria", "MF", False, "squad"),
        ("Ardon Jashari", "MF", False, "squad"),
        ("Djibril Sow", "MF", False, "squad"),
        ("Christian Fassnacht", "MF", False, "squad"),
        ("Michel Aebischer", "MF", False, "squad"),
        ("Fabian Rieder", "MF", False, "squad"),
        ("Rubén Vargas", "MF", False, "squad"),
        ("Breel Embolo", "FW", True, "starter"),
        ("Noah Okafor", "FW", False, "squad"),
        ("Dan Ndoye", "FW", False, "squad"),
        ("Zeki Amdouni", "FW", False, "squad"),
        ("Cedric Itten", "FW", False, "squad"),
    ]
}

# ═══════════════════════════════════════════════════════════
# Group C
# ═══════════════════════════════════════════════════════════

SQUADS["Brazil"] = {
    "players": [
        ("Alisson", "GK", True, "starter"),
        ("Éderson", "GK", False, "squad"),
        ("Weverton", "GK", False, "squad"),
        ("Alex Sandro", "DF", True, "starter"),
        ("Bremer", "DF", False, "squad"),
        ("Danilo", "DF", True, "starter"),
        ("Douglas Santos", "DF", False, "squad"),
        ("Gabriel Magalhães", "DF", True, "starter"),
        ("Léo Pereira", "DF", False, "squad"),
        ("Marquinhos", "DF", True, "starter"),
        ("Roger Ibañez", "DF", False, "squad"),
        ("Wesley", "DF", False, "squad"),
        ("Bruno Guimarães", "MF", True, "starter"),
        ("Casemiro", "MF", True, "starter"),
        ("Danilo Santos", "MF", False, "squad"),
        ("Fabinho", "MF", False, "squad"),
        ("Lucas Paquetá", "MF", False, "squad"),
        ("Endrick", "FW", False, "squad"),
        ("Gabriel Martinelli", "FW", False, "squad"),
        ("Igor Thiago", "FW", False, "squad"),
        ("Luiz Henrique", "FW", False, "squad"),
        ("Matheus Cunha", "FW", False, "squad"),
        ("Neymar", "FW", True, "starter"),
        ("Raphinha", "FW", True, "starter"),
        ("Rayan", "FW", False, "squad"),
        ("Vinícius Júnior", "FW", True, "starter"),
    ]
}

SQUADS["Morocco"] = {
    "players": [
        ("Yassine Bounou", "GK", True, "starter"),
        ("Munir El Kajoui", "GK", False, "squad"),
        ("Reda Tagnaouti", "GK", False, "squad"),
        ("Noussair Mazraoui", "DF", True, "starter"),
        ("Anass Salah-Eddine", "DF", False, "squad"),
        ("Youssef Belammari", "DF", False, "squad"),
        ("Achraf Hakimi", "DF", True, "starter"),
        ("Zakaria El Ouahdi", "DF", False, "squad"),
        ("Chadi Riad", "DF", False, "squad"),
        ("Nayef Aguerd", "DF", True, "starter"),
        ("Redouane Halhal", "DF", False, "squad"),
        ("Issa Diop", "DF", False, "squad"),
        ("Samir El Mourabet", "MF", False, "squad"),
        ("Ayyoub Bouaddi", "MF", False, "squad"),
        ("Neil El Aynaoui", "MF", False, "squad"),
        ("Sofyan Amrabat", "MF", True, "starter"),
        ("Azzedine Ounahi", "MF", False, "squad"),
        ("Bilal El Khannouss", "MF", True, "starter"),
        ("Ismael Saibari", "MF", False, "squad"),
        ("Abde Ezzalzouli", "FW", False, "squad"),
        ("Chemsdine Talbi", "FW", False, "squad"),
        ("Soufiane Rahimi", "FW", False, "squad"),
        ("Ayoub El Kaabi", "FW", False, "squad"),
        ("Brahim Díaz", "FW", True, "starter"),
        ("Gessime Yassine", "FW", False, "squad"),
        ("Ayoube Amaimouni", "FW", False, "squad"),
    ]
}

SQUADS["Haiti"] = {
    "players": [
        ("Johny Placide", "GK", True, "starter"),
        ("Alexandre Pierre", "GK", False, "squad"),
        ("Josué Duverger", "GK", False, "squad"),
        ("Carlens Arcus", "DF", False, "squad"),
        ("Wilguens Paugain", "DF", False, "squad"),
        ("Duke Lacroix", "DF", False, "squad"),
        ("Martin Expérience", "DF", False, "squad"),
        ("Jean-Kévin Duverne", "DF", False, "squad"),
        ("Ricardo Adé", "DF", True, "starter"),
        ("Hannes Delcroix", "DF", False, "squad"),
        ("Keeto Thermoncy", "DF", False, "squad"),
        ("Carl Fred Sainté", "MF", False, "squad"),
        ("Leverton Pierre", "MF", False, "squad"),
        ("Danley Jean Jacques", "MF", False, "squad"),
        ("Jean-Ricner Bellegarde", "MF", True, "starter"),
        ("Woodensky Pierre", "MF", False, "squad"),
        ("Dominique Simon", "MF", False, "squad"),
        ("Don Deedson Louicius", "FW", False, "squad"),
        ("Josué Casimir", "FW", False, "squad"),
        ("Derrick Etienne", "FW", False, "squad"),
        ("Ruben Providence", "FW", False, "squad"),
        ("Duckens Nazon", "FW", True, "starter"),
        ("Frantzdy Pierrot", "FW", False, "squad"),
        ("Wilson Isidor", "FW", True, "starter"),
        ("Yassin Fortuné", "FW", False, "squad"),
        ("Lenny Joseph", "FW", False, "squad"),
    ]
}

SQUADS["Scotland"] = {
    "players": [
        ("Craig Gordon", "GK", True, "starter"),
        ("Angus Gunn", "GK", False, "squad"),
        ("Liam Kelly", "GK", False, "squad"),
        ("Grant Hanley", "DF", False, "squad"),
        ("Jack Hendry", "DF", False, "squad"),
        ("Aaron Hickey", "DF", False, "squad"),
        ("Dom Hyam", "DF", False, "squad"),
        ("Scott McKenna", "DF", False, "squad"),
        ("Nathan Patterson", "DF", False, "squad"),
        ("Anthony Ralston", "DF", False, "squad"),
        ("Andy Robertson", "DF", True, "starter"),
        ("John Souttar", "DF", False, "squad"),
        ("Kieran Tierney", "DF", True, "starter"),
        ("Ryan Christie", "MF", False, "squad"),
        ("Finlay Curtis", "MF", False, "squad"),
        ("Lewis Ferguson", "MF", False, "squad"),
        ("Ben Gannon-Doak", "MF", False, "squad"),
        ("Billy Gilmour", "MF", False, "squad"),
        ("John McGinn", "MF", True, "starter"),
        ("Kenny McLean", "MF", False, "squad"),
        ("Scott McTominay", "MF", True, "starter"),
        ("Ché Adams", "FW", False, "squad"),
        ("Lyndon Dykes", "FW", False, "squad"),
        ("George Hirst", "FW", False, "squad"),
        ("Lawrence Shankland", "FW", False, "squad"),
        ("Ross Stewart", "FW", False, "squad"),
    ]
}

# ═══════════════════════════════════════════════════════════
# Group D
# ═══════════════════════════════════════════════════════════

SQUADS["United States"] = {
    "players": [
        ("Chris Brady", "GK", False, "squad"),
        ("Matt Freese", "GK", False, "squad"),
        ("Matt Turner", "GK", True, "starter"),
        ("Max Arfsten", "DF", False, "squad"),
        ("Sergiño Dest", "DF", True, "starter"),
        ("Alex Freeman", "DF", False, "squad"),
        ("Mark McKenzie", "DF", False, "squad"),
        ("Tim Ream", "DF", False, "squad"),
        ("Chris Richards", "DF", False, "squad"),
        ("Antonee Robinson", "DF", True, "starter"),
        ("Miles Robinson", "DF", False, "squad"),
        ("Joe Scally", "DF", False, "squad"),
        ("Auston Trusty", "DF", False, "squad"),
        ("Tyler Adams", "MF", True, "starter"),
        ("Sebastian Berhalter", "MF", False, "squad"),
        ("Weston McKennie", "MF", True, "starter"),
        ("Cristian Roldan", "MF", False, "squad"),
        ("Brenden Aaronson", "FW", False, "squad"),
        ("Christian Pulisic", "FW", True, "starter"),
        ("Gio Reyna", "FW", True, "starter"),
        ("Malik Tillman", "FW", False, "squad"),
        ("Tim Weah", "FW", False, "squad"),
        ("Alejandro Zendejas", "FW", False, "squad"),
        ("Folarin Balogun", "FW", True, "starter"),
        ("Ricardo Pepi", "FW", False, "squad"),
        ("Haji Wright", "FW", False, "squad"),
    ]
}

SQUADS["Paraguay"] = {
    "players": [
        ("Roberto Fernández", "GK", True, "starter"),
        ("Orlando Gill", "GK", False, "squad"),
        ("Gastón Olveira", "GK", False, "squad"),
        ("Gustavo Gómez", "DF", True, "starter"),
        ("Júnior Alonso", "DF", True, "starter"),
        ("Fabián Balbuena", "DF", False, "squad"),
        ("Omar Alderete", "DF", False, "squad"),
        ("Juan Cáceres", "DF", False, "squad"),
        ("José Canale", "DF", False, "squad"),
        ("Alexandro Maidana", "DF", False, "squad"),
        ("Gustavo Velázquez", "DF", False, "squad"),
        ("Miguel Almirón", "MF", True, "starter"),
        ("Kaku", "MF", False, "squad"),
        ("Andrés Cubas", "MF", False, "squad"),
        ("Ramón Sosa", "MF", False, "squad"),
        ("Diego Gómez", "MF", False, "squad"),
        ("Damián Bobadilla", "MF", False, "squad"),
        ("Braian Ojeda", "MF", False, "squad"),
        ("Matías Galarza", "MF", False, "squad"),
        ("Maurício", "MF", False, "squad"),
        ("Antonio Sanabria", "FW", False, "squad"),
        ("Julio Enciso", "FW", True, "starter"),
        ("Gabriel Ávalos", "FW", False, "squad"),
        ("Alex Arce", "FW", False, "squad"),
        ("Isidro Pitta", "FW", False, "squad"),
        ("Gustavo Caballero", "FW", False, "squad"),
    ]
}

SQUADS["Australia"] = {
    "players": [
        ("Mathew Ryan", "GK", True, "starter"),
        ("Paul Izzo", "GK", False, "squad"),
        ("Patrick Beach", "GK", False, "squad"),
        ("Jordan Bos", "DF", False, "squad"),
        ("Aziz Behich", "DF", False, "squad"),
        ("Harry Souttar", "DF", True, "starter"),
        ("Alessandro Circati", "DF", False, "squad"),
        ("Lucas Herrington", "DF", False, "squad"),
        ("Cameron Burgess", "DF", False, "squad"),
        ("Kai Trewin", "DF", False, "squad"),
        ("Milos Degenek", "DF", False, "squad"),
        ("Jason Geria", "DF", False, "squad"),
        ("Jacob Italiano", "DF", False, "squad"),
        ("Jackson Irvine", "MF", True, "starter"),
        ("Aiden O'Neill", "MF", False, "squad"),
        ("Paul Okon Jr", "MF", False, "squad"),
        ("Cameron Devlin", "MF", False, "squad"),
        ("Connor Metcalfe", "FW", False, "squad"),
        ("Mathew Leckie", "FW", False, "squad"),
        ("Nishan Velupillay", "FW", False, "squad"),
        ("Cristian Volpato", "FW", False, "squad"),
        ("Nestory Irankunda", "FW", True, "starter"),
        ("Awer Mabil", "FW", False, "squad"),
        ("Ajdin Hrustic", "FW", False, "squad"),
        ("Mohamed Toure", "FW", False, "squad"),
        ("Tete Yengi", "FW", False, "squad"),
    ]
}

SQUADS["Turkey"] = {
    "players": [
        ("Mert Günok", "GK", True, "starter"),
        ("Altay Bayındır", "GK", False, "squad"),
        ("Uğurcan Çakır", "GK", False, "squad"),
        ("Zeki Çelik", "DF", False, "squad"),
        ("Merih Demiral", "DF", True, "starter"),
        ("Çağlar Söyüncü", "DF", False, "squad"),
        ("Eren Elmalı", "DF", False, "squad"),
        ("Abdülkerim Bardakcı", "DF", False, "squad"),
        ("Ozan Kabak", "DF", False, "squad"),
        ("Mert Müldür", "DF", False, "squad"),
        ("Ferdi Kadıoğlu", "DF", True, "starter"),
        ("Samet Akaydin", "DF", False, "squad"),
        ("Salih Özcan", "MF", False, "squad"),
        ("Orkun Kökçü", "MF", False, "squad"),
        ("Hakan Çalhanoğlu", "MF", True, "starter"),
        ("İsmail Yüksek", "MF", False, "squad"),
        ("Kaan Ayhan", "MF", False, "squad"),
        ("Kerem Aktürkoğlu", "FW", False, "squad"),
        ("Arda Güler", "FW", True, "starter"),
        ("Deniz Gül", "FW", False, "squad"),
        ("Kenan Yıldız", "FW", True, "starter"),
        ("İrfan Can Kahveci", "FW", False, "squad"),
        ("Yunus Akgün", "FW", False, "squad"),
        ("Barış Alper Yılmaz", "FW", False, "squad"),
        ("Oğuz Aydın", "FW", False, "squad"),
        ("Can Uzun", "FW", False, "squad"),
    ]
}

# ═══════════════════════════════════════════════════════════
# Group E
# ═══════════════════════════════════════════════════════════

SQUADS["Germany"] = {
    "players": [
        ("Oliver Baumann", "GK", False, "squad"),
        ("Manuel Neuer", "GK", True, "starter"),
        ("Alexander Nübel", "GK", False, "squad"),
        ("Waldemar Anton", "DF", False, "squad"),
        ("Nathaniel Brown", "DF", False, "squad"),
        ("David Raum", "DF", False, "squad"),
        ("Antonio Rüdiger", "DF", True, "starter"),
        ("Nico Schlotterbeck", "DF", False, "squad"),
        ("Jonathan Tah", "DF", False, "squad"),
        ("Malick Thiaw", "DF", False, "squad"),
        ("Pascal Groß", "MF", False, "squad"),
        ("Nadiem Amiri", "MF", False, "squad"),
        ("Joshua Kimmich", "MF", True, "starter"),
        ("Felix Nmecha", "MF", False, "squad"),
        ("Aleksandar Pavlović", "MF", False, "squad"),
        ("Angelo Stiller", "MF", False, "squad"),
        ("Leon Goretzka", "MF", False, "squad"),
        ("Florian Wirtz", "MF", True, "starter"),
        ("Jamie Leweling", "MF", False, "squad"),
        ("Maximilian Beier", "FW", False, "squad"),
        ("Kai Havertz", "FW", True, "starter"),
        ("Lennart Karl", "FW", False, "squad"),
        ("Jamal Musiala", "FW", True, "starter"),
        ("Leroy Sané", "FW", False, "squad"),
        ("Deniz Undav", "FW", False, "squad"),
        ("Nick Woltemade", "FW", False, "squad"),
    ]
}

SQUADS["Curacao"] = {
    "players": [
        ("Eloy Room", "GK", True, "starter"),
        ("Tyrick Bodak", "GK", False, "squad"),
        ("Trevor Doornbusch", "GK", False, "squad"),
        ("Riechedly Bazoer", "DF", True, "starter"),
        ("Joshua Brenet", "DF", False, "squad"),
        ("Roshon van Eijma", "DF", False, "squad"),
        ("Sherel Floranus", "DF", False, "squad"),
        ("Deveron Fonville", "DF", False, "squad"),
        ("Jurien Gaari", "DF", False, "squad"),
        ("Armando Obispo", "DF", False, "squad"),
        ("Shurandy Sambo", "DF", False, "squad"),
        ("Juninho Bacuna", "MF", True, "starter"),
        ("Leandro Bacuna", "MF", False, "squad"),
        ("Livano Comenencia", "MF", False, "squad"),
        ("Kevin Felida", "MF", False, "squad"),
        ("Ar'jany Martha", "MF", False, "squad"),
        ("Tyrese Noslin", "MF", False, "squad"),
        ("Godfried Roemeratoe", "MF", False, "squad"),
        ("Jeremy Antonisse", "FW", False, "squad"),
        ("Tahith Chong", "FW", True, "starter"),
        ("Kenji Gorre", "FW", False, "squad"),
        ("Sontje Hansen", "FW", False, "squad"),
        ("Gervane Kastaneer", "FW", False, "squad"),
        ("Brandley Kuwas", "FW", False, "squad"),
        ("Jurgen Locadia", "FW", False, "squad"),
        ("Jearl Margaritha", "FW", False, "squad"),
    ]
}

SQUADS["Ivory Coast"] = {
    "players": [
        ("Yahia Fofana", "GK", True, "starter"),
        ("Mohamed Koné", "GK", False, "squad"),
        ("Alban Lafont", "GK", False, "squad"),
        ("Emmanuel Agbadou", "DF", False, "squad"),
        ("Clément Akpa", "DF", False, "squad"),
        ("Ousmane Diomande", "DF", True, "starter"),
        ("Guela Doué", "DF", False, "squad"),
        ("Ghislain Konan", "DF", False, "squad"),
        ("Odilon Kossounou", "DF", False, "squad"),
        ("Evan Ndicka", "DF", True, "starter"),
        ("Wilfried Singo", "DF", False, "squad"),
        ("Seko Fofana", "MF", True, "starter"),
        ("Parfait Guiagon", "MF", False, "squad"),
        ("Franck Kessié", "MF", True, "starter"),
        ("Christ Inao Oulaï", "MF", False, "squad"),
        ("Ibrahim Sangaré", "MF", False, "squad"),
        ("Jean Michaël Seri", "MF", False, "squad"),
        ("Simon Adingra", "FW", False, "squad"),
        ("Ange-Yoan Bonny", "FW", False, "squad"),
        ("Amad Diallo", "FW", True, "starter"),
        ("Oumar Diakité", "FW", False, "squad"),
        ("Yan Diomande", "FW", False, "squad"),
        ("Evann Guessand", "FW", False, "squad"),
        ("Nicolas Pépé", "FW", True, "starter"),
        ("Bazoumana Touré", "FW", False, "squad"),
        ("Elye Wahi", "FW", False, "squad"),
    ]
}

SQUADS["Ecuador"] = {
    "players": [
        ("Hernán Galíndez", "GK", True, "starter"),
        ("Moisés Ramírez", "GK", False, "squad"),
        ("Gonzalo Valle", "GK", False, "squad"),
        ("Willian Pacho", "DF", True, "starter"),
        ("Piero Hincapié", "DF", True, "starter"),
        ("Joel Ordóñez", "DF", False, "squad"),
        ("Félix Torres", "DF", False, "squad"),
        ("Pervis Estupiñán", "DF", True, "starter"),
        ("Yaimar Medina", "DF", False, "squad"),
        ("Ángelo Preciado", "DF", False, "squad"),
        ("Jackson Porozo", "DF", False, "squad"),
        ("Alan Minda", "MF", False, "squad"),
        ("Moisés Caicedo", "MF", True, "starter"),
        ("Jordy Alcívar", "MF", False, "squad"),
        ("Denil Castillo", "MF", False, "squad"),
        ("John Yeboah", "MF", False, "squad"),
        ("Alan Franco", "MF", False, "squad"),
        ("Pedro Vite", "MF", False, "squad"),
        ("Kendry Páez", "MF", False, "squad"),
        ("Nilson Angulo", "MF", False, "squad"),
        ("Gonzalo Plata", "MF", False, "squad"),
        ("Kevin Rodríguez", "FW", False, "squad"),
        ("Anthony Valencia", "FW", False, "squad"),
        ("Enner Valencia", "FW", True, "starter"),
        ("Jordy Caicedo", "FW", False, "squad"),
        ("Jeremy Arévalo", "FW", False, "squad"),
    ]
}

# ═══════════════════════════════════════════════════════════
# Group F
# ═══════════════════════════════════════════════════════════

SQUADS["Netherlands"] = {
    "players": [
        ("Mark Flekken", "GK", False, "squad"),
        ("Robin Roefs", "GK", False, "squad"),
        ("Bart Verbruggen", "GK", True, "starter"),
        ("Nathan Aké", "DF", True, "starter"),
        ("Denzel Dumfries", "DF", True, "starter"),
        ("Jorrel Hato", "DF", False, "squad"),
        ("Jurriën Timber", "DF", False, "squad"),
        ("Jan Paul van Hecke", "DF", False, "squad"),
        ("Micky van de Ven", "DF", False, "squad"),
        ("Virgil van Dijk", "DF", True, "starter"),
        ("Frenkie de Jong", "MF", True, "starter"),
        ("Marten de Roon", "MF", False, "squad"),
        ("Ryan Gravenberch", "MF", True, "starter"),
        ("Teun Koopmeiners", "MF", False, "squad"),
        ("Tijjani Reijnders", "MF", False, "squad"),
        ("Guus Til", "MF", False, "squad"),
        ("Quinten Timber", "MF", False, "squad"),
        ("Mats Wieffer", "MF", False, "squad"),
        ("Brian Brobbey", "FW", False, "squad"),
        ("Memphis Depay", "FW", True, "starter"),
        ("Cody Gakpo", "FW", True, "starter"),
        ("Justin Kluivert", "FW", False, "squad"),
        ("Noa Lang", "FW", False, "squad"),
        ("Donyell Malen", "FW", False, "squad"),
        ("Crysencio Summerville", "FW", False, "squad"),
        ("Wout Weghorst", "FW", False, "squad"),
    ]
}

SQUADS["Japan"] = {
    "players": [
        ("Zion Suzuki", "GK", True, "starter"),
        ("Keisuke Osako", "GK", False, "squad"),
        ("Tomoki Hayakawa", "GK", False, "squad"),
        ("Yūto Nagatomo", "DF", True, "starter"),
        ("Shogo Taniguchi", "DF", False, "squad"),
        ("Ko Itakura", "DF", True, "starter"),
        ("Tsuyoshi Watanabe", "DF", False, "squad"),
        ("Takehiro Tomiyasu", "DF", True, "starter"),
        ("Hiroki Ito", "DF", False, "squad"),
        ("Ayumu Seko", "DF", False, "squad"),
        ("Yukinari Sugawara", "DF", False, "squad"),
        ("Junnosuke Suzuki", "MF", False, "squad"),
        ("Wataru Endo", "MF", True, "starter"),
        ("Junya Ito", "MF", False, "squad"),
        ("Daichi Kamada", "MF", False, "squad"),
        ("Ritsu Doan", "MF", False, "squad"),
        ("Ao Tanaka", "MF", False, "squad"),
        ("Keito Nakamura", "MF", False, "squad"),
        ("Kaishu Sano", "MF", False, "squad"),
        ("Takefusa Kubo", "MF", True, "starter"),
        ("Yuito Suzuki", "MF", False, "squad"),
        ("Koki Ogawa", "FW", False, "squad"),
        ("Daizen Maeda", "FW", False, "squad"),
        ("Ayase Ueda", "FW", False, "squad"),
        ("Kento Shiogai", "FW", False, "squad"),
        ("Keisuke Goto", "FW", False, "squad"),
    ]
}

SQUADS["Sweden"] = {
    "players": [
        ("Viktor Johansson", "GK", True, "starter"),
        ("Kristoffer Nordfeldt", "GK", False, "squad"),
        ("Jacob Widell Zetterström", "GK", False, "squad"),
        ("Hjalmar Ekdal", "DF", False, "squad"),
        ("Gabriel Gudmundsson", "DF", False, "squad"),
        ("Isak Hien", "DF", True, "starter"),
        ("Emil Holm", "DF", False, "squad"),
        ("Gustaf Lagerbielke", "DF", False, "squad"),
        ("Victor Lindelöf", "DF", True, "starter"),
        ("Erik Smith", "DF", False, "squad"),
        ("Carl Starfelt", "DF", False, "squad"),
        ("Elliot Stroud", "DF", False, "squad"),
        ("Daniel Svensson", "DF", False, "squad"),
        ("Taha Ali", "MF", False, "squad"),
        ("Yasin Ayari", "MF", False, "squad"),
        ("Lucas Bergvall", "MF", False, "squad"),
        ("Jesper Karlström", "MF", False, "squad"),
        ("Ken Sema", "MF", False, "squad"),
        ("Mattias Svanberg", "MF", False, "squad"),
        ("Besfort Zeneli", "MF", False, "squad"),
        ("Alexander Bernhardsson", "FW", False, "squad"),
        ("Anthony Elanga", "FW", True, "starter"),
        ("Viktor Gyökeres", "FW", True, "starter"),
        ("Alexander Isak", "FW", True, "starter"),
        ("Gustaf Nilsson", "FW", False, "squad"),
        ("Benjamin Nygren", "FW", False, "squad"),
    ]
}

SQUADS["Tunisia"] = {
    "players": [
        ("Aymen Dahmen", "GK", True, "starter"),
        ("Sabri Ben Hessen", "GK", False, "squad"),
        ("Abdelmouhib Chamakh", "GK", False, "squad"),
        ("Montassar Talbi", "DF", True, "starter"),
        ("Dylan Bronn", "DF", False, "squad"),
        ("Omar Rekik", "DF", False, "squad"),
        ("Yan Valery", "DF", False, "squad"),
        ("Ali Abdi", "DF", False, "squad"),
        ("Moutaz Neffati", "DF", False, "squad"),
        ("Raed Chikhaoui", "DF", False, "squad"),
        ("Adam Arous", "DF", False, "squad"),
        ("Mohamed Amine Ben Hamida", "DF", False, "squad"),
        ("Ellyes Skhiri", "MF", True, "starter"),
        ("Hannibal Mejbri", "MF", True, "starter"),
        ("Anis Ben Slimane", "MF", False, "squad"),
        ("Hadj Mahmoud", "MF", False, "squad"),
        ("Rani Khedira", "MF", False, "squad"),
        ("Mortadha Ben Ouanes", "MF", False, "squad"),
        ("Elias Achouri", "FW", False, "squad"),
        ("Ismaël Gharbi", "FW", False, "squad"),
        ("Elias Saad", "FW", False, "squad"),
        ("Sebastian Tounekti", "FW", False, "squad"),
        ("Firas Chaouat", "FW", False, "squad"),
        ("Khalil Ayari", "FW", False, "squad"),
        ("Hazem Mastouri", "FW", False, "squad"),
        ("Rayan Elloumi", "FW", False, "squad"),
    ]
}

print(f"Loaded {len(SQUADS)} teams")
# Will print total count after all groups added
