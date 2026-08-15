# Custom AMSP

Ein Fork von **AMSP** (*Siril Wizard – Automatic Multi-Session Processing* von
Cyril Richard) mit **manueller Zuordnung der Kalibrierungs-Frames**.

> AMSP leitet die Zuordnung von Lights zu Bias/Darks/Flats aus der Aufnahmezeit
> ab (`DATE-OBS`, Nacht von 12 Uhr bis 12 Uhr) plus Belichtungszeit und Filter.
> Wenn diese Heuristik danebenliegt, gibt es im Original keinen Weg, sie zu
> korrigieren. Genau das macht dieser Fork möglich.

---

## Das Problem

Die automatische Zuordnung scheitert regelmäßig bei:

| Situation | Was AMSP macht |
|---|---|
| Flats erst am nächsten Nachmittag aufgenommen | eigene „Nacht" → Lights bekommen **gar kein** Flat |
| Dark-Bibliothek von einem anderen Datum | funktioniert nur, solange die Belichtungszeit exakt passt |
| Session über lokal 12 Uhr hinweg | eine Nacht wird in zwei Sessions zerlegt |
| Falsche oder fehlende `DATE-OBS` (z. B. Kamera-Uhr falsch gestellt) | Zuordnung praktisch zufällig |
| Zwei Setups in derselben Nacht | Flats des einen Setups landen bei den Lights des anderen |

In allen Fällen läuft die Pipeline scheinbar sauber durch – kalibriert wird
aber mit den falschen Frames oder gar nicht.

## Die Lösung

Ein neuer Dialog **„🎯 Calibration Assignment"** legt sich über die
Automatik. Pro Light-Gruppe (Objekt × Nacht × Filter × Belichtungszeit) wird
explizit ausgewählt, welches Bias, welches Dark und welches Flat verwendet
wird:

```
Object  Night       Filter  Exposure  Frames  Bias           Dark                        Flat
M42     2026-03-22  Ha      300s      42      Auto           Dark subs · all nights · 300s   Flat subs · 2026-03-25 · Ha
M42     2026-03-23  Ha      300s      38      Auto           Dark subs · all nights · 300s   Flat subs · 2026-03-25 · Ha
```

Ein zweiter Reiter macht dasselbe für die Flats selbst: welches Bias bzw.
welches Dark-Flat sie kalibriert.

**Jede Zeile steht anfangs auf „Auto"** – das ist exakt das bisherige
Verhalten. Der Dialog ändert nichts, solange nichts umgestellt wird.

### Kernpunkt: Quellen haben stabile IDs, kein Datum

Jede Kalibrierungsquelle bekommt eine ID, die nicht aus dem Aufnahmezeitpunkt
abgeleitet wird:

| ID | Bedeutung |
|---|---|
| `subs:dark:*:300s` | alle 300-s-Darks, **egal aus welcher Nacht** (Dark-Bibliothek) |
| `subs:dark:2026-01-05:300s` | nur die Darks dieser einen Nacht |
| `subs:flat:2026-03-25:Ha` | die Ha-Flats dieser Nacht |
| `subs:bias:*:` | alle Bias-Frames |
| `file:/pfad/master-dark.fit` | ein fertiger Master oder eine Datei aus dem „External darks"-Ordner |
| `__synthetic__` | der synthetische Bias-Ausdruck aus dem Hauptfenster |
| `__none__` | bewusst **keine** Kalibrierung dieser Art |
| `__auto__` | die bisherige automatische Zuordnung |

Weil die IDs stabil sind, überlebt eine einmal korrigierte Zuordnung Neustarts:
sie wird in der Konfigurationsdatei gespeichert.

### Weitere Ergänzungen

* **Strict-Modus** (in den Pipeline-Optionen): Kalibrierungs-Frames werden
  *ausschließlich* nach manueller Zuordnung verwendet. Alles, was auf „Auto"
  steht, bleibt unkalibriert, statt über das Datum geraten zu werden. Für den
  Fall, dass eine falsche Zuordnung schlimmer ist als gar keine.
* **Darks über alle Nächte poolen** – eine Dark-Bibliothek ist damit direkt
  auswählbar, ohne Datums-Tricks.
* **Master/Sub per Rechtsklick umschalten** – Master werden über `STACKCNT > 1`
  erkannt; viele Programme schreiben dieses Keyword nicht, wodurch ein fertiger
  Master erneut gestackt würde.
* **Dateityp-Korrektur gilt jetzt auch für Master** – ein Master-Flat mit
  falschem `IMAGETYP` lässt sich sonst gar nicht als Flat zuordnen.
* **Bugfix aus dem Original:** die Option „Save master frames to
  output/masters/" wurde nie an die Engine durchgereicht und war damit
  wirkungslos (Master wurden immer gespeichert).

Details und Beispiel-Workflows: [`docs/calibration-assignment.md`](docs/calibration-assignment.md)

---

## Installation

1. Siril 1.4 oder neuer mit aktiviertem Python-Support (`sirilpy`).
2. `Custom_AMSP.py` in das Siril-Skriptverzeichnis kopieren:
   * Linux: `~/.local/share/siril/scripts/`
   * macOS: `~/Library/Application Support/org.free-astro.siril/scripts/`
   * Windows: `%LOCALAPPDATA%\siril\scripts\`
3. In Siril unter *Scripts* aufrufen. PyQt6 und astropy installiert das Skript
   beim ersten Start selbst nach.

Die Konfiguration liegt in `custom_amsp.json` (nicht `amsp.json`), Custom AMSP
und das Original stören sich also nicht gegenseitig.

## Benutzung

1. FITS-Dateien oder Ordner in das Fenster ziehen.
2. Baumansicht prüfen; falsch erkannte Dateien per Rechtsklick korrigieren.
3. **🎯 Calibration Assignment** öffnen und die Zuordnungen setzen, die die
   Automatik nicht richtig hinbekommt.
4. **▶ Go** – die Zuordnung wird im Siril-Log protokolliert:

```
  ⚙ M42/2026-03-22/Ha/300s: flat ← Flat subs · 2026-03-25 · Ha · 25 frames
  ⚙ M42/2026-03-22/Ha/300s: dark ← Dark subs · all nights · 300s · 40 frames
```

## Tests

Ohne Siril lauffähig – `sirilpy` wird gestubbt, Qt läuft offscreen:

```bash
pip install astropy numpy PyQt6
python3 tests/test_assignment.py
```

38 Tests decken Quellen-Enumeration, Zuordnungs-Auflösung, Strict-Modus,
Fallback bei fehlenden Dateien, Konfigurations-Round-Trip und den Dialog ab.
Ein Test hält ausdrücklich fest, dass die **automatische** Zuordnung das Flat
aus einer anderen Nacht nicht findet – das ist der Ausgangsbefund, den dieser
Fork behebt.

## Lizenz

GPL-3.0-or-later, wie das Original.

* AMSP © 2026 Cyril Richard
* Änderungen für Custom AMSP © 2026 Custom AMSP contributors

---

## English summary

Custom AMSP is a fork of Cyril Richard's AMSP Siril script. Upstream infers
which calibration frames belong to which lights from the capture time; when
that guess is wrong there is no way to correct it.

This fork adds a **Calibration Assignment** dialog: per light group
(object × night × filter × exposure) you pick the exact bias, dark and flat to
use, and per flat group the bias or dark-flat that calibrates it. Sources are
addressed by stable IDs that do not depend on a capture date (raw sub groups,
pre-existing masters, external files, synthetic bias, or "None"), so a dark
library or a set of flats shot days later can be assigned directly.
Assignments persist in the config file. A **strict mode** disables date-based
matching entirely: anything left on "Auto" is simply not applied.

Every row defaults to "Auto", which is the unchanged upstream behaviour.
