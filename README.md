# G19 PC Monitor

Affiche les infos du PC sur l'écran couleur (320×240) du Logitech G19 : système, GPU,
jeux, média, Discord, et un voyant d'état des agents Claude Code.

## Alertes et rétroéclairage

- **Alertes** (onglet Alertes de l'utilitaire) : hotspot GPU, température GPU/CPU, RAM, VRAM,
  disques. Au-delà du seuil pendant 5 s : bandeau rouge, cadre rouge clignotant et pastille
  ⚠ dans le bandeau ; l'alerte tombe 5 unités sous le seuil.
- **Rétroéclairage du G19 comme voyant** : clignote pendant une alerte (rouge), pulse quand
  Claude attend ta réponse (jaune), couleur fixe pendant que Claude travaille (orange, en
  option), clignote quand Claude a fini (vert), à chaque message Discord (bleu) et à chaque
  notification Windows (blanc). Chaque effet se désactive séparément et a **sa couleur, réglable**
  (pastille dans l'onglet Alertes et clavier) ; le nombre de clignotements (1 à 10) se règle par
  effet ; la vitesse de clignotement (60 à 1000 ms) et celle de la pulsation (30 à 300 ms) se
  règlent au curseur. Boutons « Tester » dans l'utilitaire et dans le menu du G19.
  Après un effet, le clavier repasse dans sa **couleur au repos** (blanc par défaut, réglable ;
  « Restaurer » réapplique plutôt l'éclairage sauvegardé avant le premier effet). Le reste du temps, l'éclairage choisi dans LGS est rétabli. LGS doit
  autoriser les jeux à contrôler l'éclairage.

## Ventilateurs

Sur la page **Système**, **OK** ouvre le panneau des ventilateurs : RPM de chacun (CPU,
système, GPU ; la pompe n'est pas listée, elle n'est jamais pilotée) et choix du profil (◄ ► choisir, OK appliquer, Annuler fermer).

Profils auto (GCC) / silencieux 35 % / équilibré 55 % / performance 75 % / maximum 100 %,
aussi dans le menu du G19 ou l'onglet Système de l'utilitaire. GCC n'étant pas pilotable, ça passe
par LibreHardwareMonitor (serveur web activé), qui règle les sorties PWM de la carte mère.
Sécurités : la pompe et le ventilo GPU ne sont jamais touchés, 30 % minimum, retour en auto
si le CPU dépasse 85 °C ou le hotspot GPU 95 °C (seuils réglables de 60 à 100 °C dans le menu
du G19 et l'onglet Système ; sauf profil maximum). Ce retour en auto est temporaire : le
réglage n'est pas modifié, et le profil choisi revient tout seul une fois le CPU et le GPU
redescendus 8 °C sous les seuils pendant une minute — durée réglable de 10 à 900 s (« Auto · chaud » sur l'écran principal,
compte à rebours dans le panneau des ventilateurs), et à la fermeture de
l'appli. Si l'appli est tuée brutalement, la vitesse reste fixée jusqu'au redémarrage de LHM.

## Thèmes

Dix-huit thèmes pour l'écran du G19 (l'utilitaire prend le même) : **sombre**, **clair**, **rétro G15**
(écran monochrome ambre à 5 niveaux avec trame de pixels LCD), **néon** (violet profond, cyan et
magenta avec une lueur), **dynamique** (l'accent et une teinte des fonds suivent la pochette en
cours, sinon la pochette du jeu lancé) et **G19 (origine)**,
façon interface de 2010 : bandeau chromé avec liseré bleu, panneaux vernis à reflet,
barres brillantes, barre de sélection bleue dans le menu, fond dégradé bleu nuit, courbes sur
matrice de LED (historiques), barres en segments de LED, jauges à lunette chromée et segments
lumineux, lecteur média avec pochette vernie et son reflet, boutons ronds chromés. Et aussi :
**haut contraste** (noir pur, blanc et jaune : le plus lisible sur le LCD), **glacier**
(bleu-gris froid), **braise** (noir chaud et orange incandescent), **terminal** (phosphore vert
d'écran cathodique, avec lignes de balayage et légère lueur) et **rouge nuit** (tout en rouge
sur noir pur, qui n'éblouit pas : idéal comme « Thème la nuit » du mode nuit).

Six thèmes changent aussi la forme des éléments (`g19/looks.py`), comme le thème G19 :
- **Aero (verre)** : fond d'écran Windows flouté, panneaux en verre translucide avec reflet,
  jauges sous verre, barres brillantes.
- **Cadrans analogiques** : jauges à aiguille sur cadran ivoire (graduations, zone rouge,
  moyeu laiton), historiques sur bande d'enregistreur quadrillée, panneaux à vis, police
  Franklin Gothic.
- **HUD cockpit** : pas de panneaux pleins, seulement des coins de cadre ; jauges en
  graduations, barres en échelles de traits, trame de points, police à chasse fixe
  (Cascadia Mono), légère lueur.
- **Tron (vectoriel)** : contours lumineux, grille au sol en perspective, arcs fins avec point
  lumineux au bout, lueur.
- **Papier (encre)** : fond crème à grain, panneaux à ombre portée, barres hachurées, jauges
  graduées à l'encre, police Times.
- **Papier sombre** : les mêmes formes, encre crème sur papier charbon.
- **Pixel 8 bits** : boîtes à coins en escalier, barres et jauges en blocs, historiques en
  colonnes de cases, textes sans lissage, palette limitée de console (pochettes comprises).

**Émojis et symboles** : un caractère absent de la police du thème est pris dans Segoe UI
Emoji (en couleur) ou Segoe UI Symbol (`g19/textfx.py`), partout : messages Discord,
titres, pseudos, notifications. Sans moteur de mise en forme, les émojis composés sont
simplifiés (👍🏽 → 👍, 👨‍👩‍👧 → 👨) et les drapeaux s'affichent en lettres (« FR »).

**Fond d'écran** (option de tous les thèmes, menu du G19 ou onglet Affichage) : le fond
d'écran Windows, flouté et assombri (réglable), derrière les pages, avec des panneaux
translucides ; suit les changements de fond d'écran, diaporama compris.
« Thème » dans le menu du G19 ou l'onglet Affichage de l'utilitaire.

Chaque modification de réglage est notée (avec le programme qui l'a faite) dans
`%LOCALAPPDATA%\G19Monitor\settings_changes.log`. L'utilitaire demande d'enregistrer si on le
ferme avec des modifications en cours.

## Zone de notification

L'appli a une icône dans la zone de notification de Windows (mini écran G19, avec la pastille
du voyant Claude et un point violet s'il y a des messages Discord non lus). Survol : CPU,
GPU, FPS et état Claude. Clic : configuration. Menu : choisir la page affichée sur le G19,
journal, redémarrer, quitter.

## Navigation (touche Menu)

La touche **Menu** ouvre un carrousel « coverflow » de tous les écrans en miniatures (en
direct), en perspective avec leur reflet : ◄ ► font glisser les cartes, OK ouvre l'écran, Menu
ou Annuler ferment. La dernière carte, **Paramètres**, ouvre le menu des réglages.

## Écran du G19

Luminosité, contraste, tons sombres (gamma : au-dessus de 100 %, les gris foncés et textes
estompés ressortent mieux sur le LCD), saturation et netteté renforcée, appliqués à chaque image
(page « Écran du G19 » de l'utilitaire ou section « Réglage de l'écran » du menu du G19). La
**mire** (marches de gris, couleurs, textes de 8 à 16 px) s'affiche 20 s sur le clavier pour
régler à l'œil.

## Mode nuit

Entre deux heures réglables (23:00 → 07:00 par défaut) : écran assombri (luminosité réglable),
thème imposé si choisi, et clavier discret (seules les alertes clignotent). Menu du G19
(section Mode nuit) ou onglet Affichage de l'utilitaire.

## Bandeaux

En plus des messages Discord et des notifications Windows : arrivée / départ de quelqu'un dans
le salon vocal Discord où tu es (avec sa photo), changement de morceau, connexion
d'un périphérique (USB, Bluetooth, avec sa batterie s'il en a une), connexion et déconnexion
d'un périphérique audio (casque, enceintes, micro : un seul bandeau par appareil), batterie faible,
réseau en jeu, et « Paramètres enregistrés » quand l'utilitaire enregistre des réglages.

## Streaming entrant

Quand quelqu'un se connecte à ce PC avec Moonlight (via Sunshine) ou Parsec : bandeau rouge « connecté en streaming » (avec le pseudo pour Parsec), puis un petit écran rouge dans la barre du haut tant que la session dure, et un bandeau à la déconnexion avec sa durée. Détecté en suivant les journaux de Sunshine (`Program Files\Sunshine\config\sunshine.log`) et de Parsec (`%APPDATA%\Parsec\log.txt`). Les connexions arrivées pendant une absence figurent dans le résumé au retour.

## PC au repos

- **Horloge** : Windows verrouillé, ou ni clavier ni souris depuis 5 min (réglable), et
  l'écran du G19 passe sur une grande horloge avec la date, la météo et le compte de ce qui
  est arrivé entre-temps. Pas pendant un jeu ni quand une appli garde l'écran allumé (vidéo).
  Une touche du G19 réveille l'écran ; les bandeaux s'affichent toujours par-dessus.
- **Résumé au retour** : après au moins 5 min d'absence (réglable), un écran « Pendant ton
  absence » liste les messages Discord (regroupés par auteur), arrivées dans l'appel, amis
  Steam, téléchargements Steam terminés, agents Claude qui ont fini ou attendent, alertes,
  périphériques… Il se ferme tout seul après 45 s ou avec une touche.

## Fin de partie, alertes système, sauvegarde

- **Récapitulatif de fin de partie** : quand un jeu se ferme, le G19 affiche 20 s (ou jusqu'à
  une touche) la durée, les FPS moyen / 1 % low / max, les températures max GPU et CPU, la
  puissance moyenne et la courbe des FPS.
- **Nouveau pilote AMD** (bandeau, rappel une fois par jour) : la version d'AMD Software
  installée est comparée au catalogue de téléchargement qu'AMD Software tient à jour dans
  `%LOCALAPPDATA%\AMD_Common` (pour ta carte et ta version de Windows ; rien n'est
  téléchargé par l'appli). Installation depuis AMD Software.
- **Alertes système** (bandeau, rappel toutes les 6 h) : Windows attend un redémarrage après
  des mises à jour ; un disque passe sous l'espace libre réglé (15 Go par défaut).
- **Sauvegarde des réglages** (onglet Système de l'utilitaire) : export en .zip (réglages,
  et au choix les accès Discord / Steam et les historiques), import qui garde d'abord l'état
  actuel dans `avant_import_<date>.zip` puis redémarre l'appli.

## Configuration

**Sur le G19** : touche **Menu** → section **Ouvrir** (l'appli liée à la page affichée :
Discord, lecteur média, relancer le dernier jeu, Afterburner, Claude, gestionnaire des
tâches… puis tes raccourcis, réglables dans l'onglet Raccourcis de l'utilitaire), puis les
réglages (rétroéclairage, bandeaux, alertes, durée des bandeaux, page en jeu, fluidité,
ouvrir la config PC, redémarrer). ▲ ▼ choisir,
OK / ► changer, ◄ dans l'autre sens, Menu ou Annuler pour fermer.

**Clavier virtuel** : dans l'utilitaire, l'aperçu « ● G19 en direct » montre l'écran réellement
affiché sur le G19, et le pavé dessous (Menu, Annuler, ▲ ▼ ◀ ▶, OK) envoie les touches à l'appli
comme le vrai clavier — menu, panneau des ventilos, paroles, etc. Au clavier de l'ordinateur :
clic sur l'écran puis flèches, Entrée = OK, Échap = Annuler, M = Menu.

**Sur le PC** : clic sur l'icône, ou double-clic sur **`config_g19.pyw`** : choix et ordre des pages, page de démarrage, page
affichée au lancement d'un jeu, fluidité, Discord, démarrage avec Windows, voyant Claude,
état des sources, avec un aperçu en direct. Les réglages s'appliquent à chaud.

## Pages (◄ ► pour changer, Annuler = première page)

Les pages Discord et Docker sont masquées tant que l’appli (ou le moteur Docker) ne tourne pas, et reviennent seules à son lancement, avec un bandeau « Page Discord de nouveau disponible ».

| Page | Contenu | Boutons |
|---|---|---|
| **Système** | CPU (+ historique), GPU, VRAM, RAM, réseau, disques, encart Claude | |
| **GPU** | FPS, frametime ; en jeu, graphe des FPS (échelle resserrée : les chutes se voient) et graphe des temps d'image en direct (une barre par image du G19 : orange au-delà de 1,5× la médiane, rouge pour une saccade), les deux à la fois ou l'un des deux ; FPS moyen, 1 % low, nombre de saccades, jauges charge/temp./puissance, fréquences, hotspot, VRAM, ventilo, CPU, tension | OK (en jeu) : FPS + temps d'image → FPS → temps d'image (gardé entre deux lancements) |
| **Jeux** | En jeu : pochette, launcher, durée de session, temps du jour, temps total, FPS moy./1 % low, temp. max, graphe FPS de la session. Sinon : derniers jeux joués | |
| **Steam** | Téléchargements et mises à jour en cours (bannière du jeu, état, progression, vitesse) : tailles d'après les manifestes et `logs\content_log.txt`, progression en direct d'après le dossier `steamapps\downloading` (Steam ne met le manifeste à jour que par à-coups) ; amis en ligne et leur jeu (clé d'API Web Steam à coller dans l'onglet Steam de l'utilitaire) | ▲ ▼ défiler les amis · OK ouvrir la liste d'amis |
| **Notifs** | Notifications Windows de toutes les applis (icône, appli, titre, texte) | OK effacer |
| **Météo** | Conditions actuelles (température, ressenti, humidité, vent, pluie, soleil), 8 prochaines heures, 5 jours — Open-Meteo ; ville réglée dans l'utilitaire, sinon position d'après l'IP (ipwho.is) | |
| **VPN** | Tailscale (état, IP, tailnet, nœud de sortie, appareils en ligne, direct/relais), autres VPN (OpenVPN, WireGuard…), IP publique et fournisseur | OK connecter / couper Tailscale |
| **Débit** | Test de débit Cloudflare : ping, gigue, descendant, montant, jauge en direct, historique. Tous les tests sont gardés dans `speedtests.csv` (bouton « Historique des débits » de l'utilitaire, s'ouvre dans Excel) | OK lancer / annuler |
| **Média** | Pochette, titre, artiste, temps écoulé/total, volume + vumètre, couleur d'accent tirée de la pochette. **OK** : paroles synchronisées (LRCLIB) à la place du lecteur | ▲ préc. · OK paroles · ▼ suiv. (lecture/pause : touche média du G19) |
| **Audio** | Sortie et entrée par défaut de Windows (choix parmi les périphériques actifs), volume général et micro avec vumètres, volume de chaque appli. Les réglages s'appliquent directement au système | ▲ ▼ volume général · OK régler, puis ▲ ▼ ligne · ◄ ► volume / périphérique · OK muet / appliquer · Annuler sortir |
| **Discord** | Salon vocal (qui parle, qui est muet), ton état micro, derniers messages. En haut de chaque page, tant que Discord est ouvert : casque (vert en vocal, gris hors vocal, barré rouge en sourdine) et micro barré rouge quand tu es muet | OK muet · ▲ sourdine |
| **Claude** | Sessions Claude Code actives avec leur contexte (« ctx 154k »), l'état Git de leur dossier (branche, ●N fichiers modifiés, ↑ commits à pousser, ↓ à tirer) et, si GitHub CLI (`gh`) est installé et connecté, la PR de la branche et sa CI (ok / en cours / échec), usage du bloc de 5 h en cours (jetons, réponses, heure de remise à zéro) et des 7 derniers jours, compté depuis les transcripts locaux | ▲ ▼ choisir une session · OK la mettre au premier plan (terminal ou appli Claude) |
| **Cœurs** | Charge par thread, température et fréquence CPU | |
| **Historique** | Les dernières 24 h (une mesure par minute, gardée entre les redémarrages) : températures ou charges CPU et GPU, maximum de la journée et son heure, moyenne | OK températures / charges |
| **Docker** | Conteneurs (ceux qui tournent en premier) : état, image, CPU et RAM avec barres, code de sortie et nombre de redémarrages, total CPU / RAM ; « Docker arrêté » si Docker Desktop ne tourne pas. Bandeau quand un conteneur s'arrête en erreur ou redémarre en boucle (3 fois en 5 min) | ▲ ▼ défiler |
| **Écran PC** | Recopie en direct (~55 i/s, limitée par la fluidité réglée) d’un écran du PC, avec un repère à la place du curseur. La capture ne tourne que quand la page est affichée | OK écran suivant · ▲ ▼ zoom ×1 / ×2 / ×4 autour du curseur |
| **Batteries** | Batterie des appareils Bluetooth (casque…), connectés ou non, relue chaque minute ; bandeau sous 20 % | |
| **Réseau** | Ping chaque seconde (cible réglable, 1.1.1.1 par défaut) : latence, moyenne, min/max, gigue, perte, graphe des 2 dernières minutes. En jeu, bandeau sur un pic de latence ou des pertes | |

Le bandeau du haut indique le nom de la page et sa position (« GPU 2/11 » ; la date sur
la page Système) et montre le voyant Claude (masqué si Claude est fermé) (🟠 travaille · 🟡 attend ta réponse ·
🟢 terminé) et un badge Discord (messages non lus, point vert/rouge si en vocal).
Un message Discord reçu s'affiche quelques secondes en bas de n'importe quelle page, dans un
bandeau qui monte du bas de l'écran puis redescend.
L'écran se rouvre sur la dernière page affichée.

## Lancer, démarrage auto, mise à jour

- Lancer : double-clic sur `start_g19.pyw` (pas de console). Un écran de démarrage animé
  s'affiche sur le G19 pendant le chargement (une touche « G19 » vernie qui tombe en place, une pastille par module, barre de
  progression, fondu d'entrée et de sortie). Une seule instance à la fois ;
  au démarrage de Windows elle attend Logitech Gaming Software.
- Démarrage avec Windows : case dans l'utilitaire, ou copier `start_g19.pyw` dans
  `shell:startup`.
- Mise à jour : quand le code change, l'appli se relance seule (un code cassé est refusé et
  noté dans `g19.log`). `update.cmd` met à jour les dépendances et relance.
- `python g19_monitor.py --stop` / `--restart` / `--preview dossier`.
- **Lancée par un agent Claude** (Claude Code) : son bac à sable peut montrer à l'appli une
  copie isolée de `%LOCALAPPDATA%\G19Monitor`, et ses relances automatiques en héritent ;
  les réglages de l'utilitaire ne lui parviennent alors pas. L'appli le détecte, le note dans
  `g19.log` et affiche un bandeau toutes les 10 min : la quitter (zone de notification →
  Quitter ; « Redémarrer » ne suffit pas) et la relancer depuis Windows (`start_g19.pyw`).
- Chien de garde : si la boucle principale reste figée 45 s (pilote, DLL…), la pile de chaque fil est notée dans `g19.log`, les ventilateurs repassent en auto (la sécurité thermique tourne dans cette boucle) et une instance neuve est lancée. Une tâche périodique en erreur (capteurs, alertes, absence…) est notée et sautée sans arrêter l'appli.

## Installer sur un autre PC

`python build_package.py` crée `dist\G19Monitor-AAAAMMJJ.zip` (code seulement : ni réglages,
ni accès Discord / Steam, ni historiques). Sur l'autre PC : décompresser, double-clic sur
`Installer.cmd` — Python est trouvé ou proposé (winget), l'appli est copiée dans
`%LOCALAPPDATA%\Programs\G19Monitor` sans droits administrateur, les bibliothèques sont
installées, raccourcis sur le Bureau et dans le menu Démarrer ; démarrage avec Windows et
hooks Claude Code sur demande. `Desinstaller.cmd` retire tout (réglages gardés si on veut).
Les réglages se reprennent avec l'export / import de l'utilitaire (onglet Système).

## Sources

- **MSI Afterburner** + **RTSS** : capteurs GPU/CPU et FPS. Désactive l'affichage LCD
  Logitech d'Afterburner (onglet Monitoring) pour éviter un doublon.
- **LibreHardwareMonitor** (optionnel) : complète (tension…). *Options → Remote Web Server → Run*.
- **Jeux, tous launchers** : n'importe quel jeu est détecté par RTSS. Le nom vient de Steam,
  Epic, Xbox/Game Pass ou des programmes installés (Ubisoft, EA, Riot, Battle.net, GOG,
  Rockstar…), sinon des infos de l'exe. Pochette : Steam (local, puis recherche du jeu sur le
  store Steam), sinon l'icône de l'exe. Temps total : celui de Steam, sinon le temps suivi
  par l'appli.
- **Notifications Windows** : toutes les notifications (bandeau + page Notifs). Accès réglé
  dans Paramètres → Confidentialité et sécurité → Notifications.
- **Discord** : RPC local avec ta propre application Discord (onglet Discord de l'utilitaire,
  ou `python setup_discord.py`).
- **Média / volume** : contrôles média et Core Audio de Windows.
- **Claude Code** : hooks (`install_hooks.py`, ou case dans l'utilitaire) qui écrivent
  l'état de chaque session dans `~/.claude/g19/sessions/`.

Données de l'appli (réglages, page, historique des jeux, accès Discord) :
`%LOCALAPPDATA%\G19Monitor`, hors du dossier du code : les mises à jour n'y touchent pas.
`settings.json` garde sa version précédente dans `settings.bak.json`. Le menu du G19 et
l'utilitaire n'enregistrent que les réglages qu'ils modifient, et l'utilitaire reprend à chaud
ceux changés depuis le G19.

## Prérequis

Logitech Gaming Software (LCore.exe), Python 3 et `pip install -r requirements.txt`.
