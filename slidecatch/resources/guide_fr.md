# SlideCatch — Guide d'utilisation

SlideCatch observe une présentation partagée dans Microsoft Teams (ou tout autre programme) et garde une image de chaque diapositive. À la fin, vous vérifiez les diapositives puis vous les enregistrez en PowerPoint, en PDF ou en images.

## Démarrage rapide

1. **Choisissez quoi capturer.** Sous *Que capturer*, sélectionnez la fenêtre de la réunion (elle est en général déjà choisie).
2. **Vérifiez l'aperçu en direct.** La diapositive est entourée d'un trait pointillé : seule cette partie est gardée.
3. **Nommez la session** (facultatif) puis cliquez sur **Démarrer la capture**. La fenêtre principale se masque et une petite barre apparaît en haut de l'écran.
4. À la fin de la présentation, cliquez sur **Arrêter** dans la barre. La fenêtre de vérification s'ouvre.
5. Vérifiez les diapositives puis cliquez sur **Exporter**.

## Choisir quoi capturer

**Fenêtre** (recommandé pour Teams)

- La fenêtre de la réunion peut rester **derrière d'autres fenêtres** pendant que vous travaillez — mais ne la **réduisez** pas.
- SlideCatch trouve seul la diapositive partagée dans la fenêtre et exclut la conversation, la barre d'outils et les vignettes vidéo (*Zone de la diapositive, trouvée automatiquement*).
- *Ajuster la zone…* permet de tracer vous-même la zone sur une image de la fenêtre. *Fenêtre entière* capture tout.

**Zone de l'écran**

- *Tracer la zone à l'écran*, puis faites glisser un rectangle autour de la diapositive. **Échap** pour annuler.
- La zone doit rester visible à l'écran pendant la capture.

## Pendant la capture

La petite barre affiche la durée, le nombre de diapositives et la dernière diapositive.

| Bouton | Raccourci | Effet |
|---|---|---|
| Pause / Reprendre | Ctrl+Alt+P | Arrête de regarder l'écran un moment |
| Appareil photo | Ctrl+Alt+C | Capture la diapositive tout de suite, même si elle a peu changé |
| Arrêter | Ctrl+Alt+S | Termine la capture et ouvre la vérification |
| Flèche | — | Affiche la fenêtre principale |

Les raccourcis fonctionnent même quand Teams est au premier plan. La barre n'apparaît jamais dans les diapositives, et vous pouvez la déplacer.

**Bon à savoir**

- Une nouvelle diapositive est gardée environ une seconde après son apparition : SlideCatch attend que l'image soit stable (fin d'une transition, écran partagé net).
- Revenir à une diapositive précédente ne l'ajoute pas deux fois.
- Le pointeur de la souris et les webcams sont ignorés.
- Chaque diapositive est enregistrée sur le disque dès sa capture. Si l'ordinateur s'arrête, SlideCatch propose de restaurer la session au démarrage suivant.

## Vérifier et exporter

- **Cliquez** sur une diapositive pour la sélectionner, **Ctrl+clic** ou **Maj+clic** pour en sélectionner plusieurs.
- **Faites glisser** les diapositives pour changer leur ordre, ou utilisez les flèches.
- **Rogner** garde seulement une partie des diapositives sélectionnées. **Supprimer** (ou la touche **Suppr**) les retire.
- **Annuler** / **Rétablir** (Ctrl+Z / Ctrl+Y) reviennent sur n'importe quel changement.
- Quand une diapositive apparaît étape par étape (puce après puce), SlideCatch affiche les étapes et propose **Garder la dernière étape**.
- **Double-cliquez** sur une diapositive pour la voir en grand.

Formats d'export :

- **PowerPoint (.pptx)** — une diapositive par capture, avec une diapositive de titre et l'heure de capture dans les notes (au choix).
- **PDF** — une page par diapositive.
- **Images** — fichiers PNG dans un dossier.

Les images capturées ne sont jamais modifiées : rognages, suppressions et ordre sont appliqués à l'export.

## Paramètres (bouton engrenage)

- **Intervalle de capture** — fréquence de vérification de l'écran (1 seconde minimum).
- **Sensibilité de détection** — *Basse* : seulement les diapositives nettement différentes ; *Moyenne* : recommandée ; *Élevée* : aussi chaque étape d'une diapositive animée.
- **Ignorer le pointeur et les vignettes vidéo** — recommandé.
- **Fusionner automatiquement les étapes d'animation** — garde seulement la dernière étape des diapositives animées pendant la capture.
- **Raccourcis actifs dans tous les programmes**, **Thème** (clair, sombre, système), **Langue**, **Dossier des sessions**.

## Un problème ?

| Ce que vous voyez | Que faire |
|---|---|
| « La fenêtre est réduite » | Restaurez la fenêtre ; elle peut rester derrière les autres. |
| Trop de diapositives semblables | Baissez la sensibilité, ou ajustez la zone pour exclure les parties qui bougent. |
| Une diapositive manque | Augmentez la sensibilité, ou appuyez sur Ctrl+Alt+C pendant la réunion. |
| Aperçu noir | Choisissez *Zone de l'écran* et gardez la réunion visible. |
| « Le fichier est ouvert dans un autre programme » | Fermez le PowerPoint ou le PDF, puis exportez de nouveau. |

## Confidentialité

Tout reste sur votre ordinateur : SlideCatch n'envoie jamais rien sur Internet. Demandez l'accord du présentateur avant de capturer, comme pour l'enregistrement d'une réunion.

SlideCatch {APP_VERSION} — © {APP_YEAR} {APP_AUTHOR}
