# Manuelle Zuordnung der Kalibrierungs-Frames

Dieses Dokument beschreibt, wie Custom AMSP entscheidet, welches Bias, Dark und
Flat auf welche Lights angewendet wird – und wie man diese Entscheidung
übersteuert.

## 1. Wie das Original zuordnet

AMSP baut aus `DATE-OBS` einen „Session"-Schlüssel (Nacht von 12 Uhr bis
12 Uhr) und leitet daraus alles Weitere ab:

| Master | Automatische Auswahl im Original |
|---|---|
| Bias | kamera-weit, alle Bias-Subs werden zusammen gestackt |
| Dark | bester Treffer nach Belichtungszeit, dann CCD-Temperatur – über alle Sessions hinweg |
| Flat | **exakt dieselbe Session** und derselbe Filter; optional die zeitlich nächstgelegene Session („Use nearest flat") |
| Dark-Flat | Dark, dessen Belichtungszeit innerhalb von 20 % zur Flat-Belichtung passt |

Die Flats sind der kritische Punkt: Ohne Treffer in derselben Nacht werden die
Lights **ohne Flat** kalibriert – ohne Fehlermeldung, nur eine Zeile im Log.

## 2. Quellen und ihre IDs

Custom AMSP zählt beim Öffnen des Dialogs alle möglichen Quellen auf
(`enumerate_cal_sources`). Jede bekommt eine stabile ID:

```
subs:<art>:<nacht|*>:<qualifier>     Rohframes, werden bei Bedarf gestackt
file:/absoluter/pfad.fit             fertige Datei (Master oder External-Dark)
__auto__ / __none__ / __synthetic__  Sonderfälle
```

Beispiele:

| ID | Label im Dialog |
|---|---|
| `subs:bias:*:` | `Bias subs · all nights · 60 frames` |
| `subs:dark:*:300s` | `Dark subs · all nights · 300s · 40 frames` |
| `subs:dark:2026-01-05:300s` | `Dark subs · 2026-01-05 · 300s · 20 frames` |
| `subs:flat:2026-03-25:Ha` | `Flat subs · 2026-03-25 · Ha · 25 frames` |
| `file:/data/lib/masterdark_300s.fit` | `Master · masterdark_300s.fit · 300s` |

Pro-Nacht-Einträge erscheinen nur, wenn es mehr als eine Nacht gibt – bei einer
einzigen Nacht wäre der Eintrag identisch mit dem gepoolten.

## 3. Der Dialog

**Reiter „Lights"** – eine Zeile pro Gruppe aus Objekt × Nacht × Filter ×
Belichtungszeit, mit je einer Auswahl für Bias, Dark und Flat.

**Reiter „Flats"** – eine Zeile pro Flat-Gruppe (Nacht × Filter), mit der
Auswahl, welches Bias bzw. Dark-Flat diese Flats vor dem Stacken kalibriert.
Darks stehen hier bewusst mit zur Auswahl: ein Dark mit passender
Belichtungszeit ist der klassische Dark-Flat-Ersatz.

Hilfsschaltflächen:

* **Copy first row to all rows** – erste Zeile auf alle Zeilen des aktiven
  Reiters übertragen. Praktisch, wenn ein Kalibrierungssatz für das ganze
  Projekt gilt.
* **Reset tab to Auto** – Reiter zurücksetzen.

## 4. Auflösungsreihenfolge in der Engine

Für jede Gruppe und jede Kalibrierungsart (`_resolve_cal`):

1. **Keine Zuordnung / `__auto__`**
   * Strict-Modus aus → automatische Zuordnung des Originals
   * Strict-Modus an → **nichts** anwenden, Warnung ins Log
2. **`__none__`** → nichts anwenden
3. **`__synthetic__`** → synthetischer Bias-Ausdruck (nur für Bias)
4. **Quellen-ID** → Master aus der Registry; ist er noch nicht gebaut, wird er
   jetzt gebaut
5. **Quelle nicht auffindbar** (Datei gelöscht, Ordner nicht mehr da) →
   Warnung und Rückfall auf die Automatik; im Strict-Modus wird nichts
   angewendet

Die Regel „ein Dark enthält den Bias bereits, also nie `-bias=` und `-dark=`
zusammen an `calibrate` übergeben" gilt unverändert – sie wird nach der
Auflösung angewendet, egal ob automatisch oder manuell zugeordnet.

## 5. Wann werden zugeordnete Master gebaut?

| Phase | Automatik | Zusätzlich |
|---|---|---|
| 1 – Bias | gepooltes Master-Bias | jede zugeordnete Bias-Quelle |
| 2 – Darks | pro Nacht × Belichtungszeit | jede zugeordnete Dark-/Dark-Flat-Quelle, auch gepoolte |
| 3 – Flats | pro Nacht × Filter | jede zugeordnete Flat-Quelle, auch für Filter, die sonst übersprungen würden |

Zugeordnete Master heißen `cal_*.fit` statt `master-*.fit`. Das ist Absicht:
die automatischen Suchen arbeiten mit den Mustern `master-bias*`,
`master-dark_*` und `master-flat-*`. Ein bewusst zugeordneter Master soll
**nicht** nebenbei zum Kandidaten für die automatische Zuordnung einer anderen
Gruppe werden.

Frames werden nicht doppelt gestackt: Wenn eine „all nights"-Quelle nur Frames
aus einer einzigen Nacht enthält, wird das bereits gebaute Master dieser Nacht
wiederverwendet (`↻` im Log).

## 6. Beispiel-Workflows

### Flats vom nächsten Nachmittag

Lights vom 22. und 23. März, Flats erst am 25. März aufgenommen.

1. Alles einladen.
2. Dialog öffnen, Reiter *Lights*.
3. In der ersten Zeile *Flat* auf `Flat subs · 2026-03-25 · Ha` stellen.
4. **Copy first row to all rows** (falls alle Zeilen dasselbe Flat brauchen).

Ohne diesen Schritt bekommen beide Nächte gar kein Flat.

### Dark-Bibliothek

Darks stammen aus einer Bibliotheksnacht oder liegen als fertige Master in
einem Ordner.

* Rohframes: *Dark* auf `Dark subs · all nights · 300s` stellen.
* Fertige Master: Ordner unter *External darks* wählen, dann den Eintrag
  `External · masterdark_300s.fit` – damit entfällt jede Toleranzrechnung über
  Belichtungszeit und Temperatur.

### Zwei Setups in einer Nacht

Beide Setups liefern Lights derselben Nacht, aber jeweils eigene Flats.
Da die Zeilen nach Objekt, Filter und Belichtungszeit getrennt sind, lässt sich
jeder Gruppe ihr eigenes Flat zuweisen – solange sich die Gruppen in mindestens
einem dieser Merkmale unterscheiden. Andernfalls hilft es, die Frames des
zweiten Setups in einem separaten Durchlauf zu verarbeiten.

### Kaputte `DATE-OBS`-Header

Wenn die Kamera-Uhr falsch stand, ist die Nacht-Spalte unbrauchbar. Dann:

1. *Strict assignment* in den Pipeline-Optionen aktivieren.
2. Für jede Zeile Bias, Dark und Flat explizit auswählen.

Damit stammt keine einzige Zuordnung mehr aus einem Datum.

## 7. Der Assistent

Der Assistent (Knopf **🧙 Assistent**) ist eine geführte Oberfläche für genau
dieselben Zuordnungen. Er schreibt am Ende in dieselben Tabellen, die in
Abschnitt 4 aufgelöst werden – es gibt keinen zweiten Codepfad.

Unterschiede zum Dialog:

| | Dialog | Assistent |
|---|---|---|
| Granularität | Light-Gruppe (Objekt × Nacht × Filter × Belichtung) | Nacht (wird beim Übernehmen auf alle Gruppen der Nacht ausgerollt) |
| Vorauswahl | „Auto" | konkrete Quelle, sichtbar in der Zeile |
| Dark-Flat | im Reiter *Flats* pro Flat-Gruppe | eigene Spalte pro Nacht, landet auf der Flat-Gruppe der gewählten Flats |
| Prüfung | keine | Belichtungszeit und Datum, mit Bestätigungspflicht |

### Prüfungen im Detail

**Belichtungszeit (Standard ±5 s).** Verglichen wird die häufigste
Belichtungszeit der Lights einer Nacht mit der des zugeordneten Darks, und die
häufigste Belichtungszeit der Flats mit der des zugeordneten Dark-Flats. Liegt
die Abweichung über der Toleranz, erscheint eine Warnung mit beiden Werten.

**Flat-Datum (Standard ±1 Tag).** Verglichen werden die Nacht-Schlüssel. Weil
der Schlüssel von 12 bis 12 Uhr läuft, ist ein Flat vom Nachmittag nach der
Nacht genau einen Tag entfernt und damit in Ordnung; ein Flat zwei Tage später
wird gemeldet. Fehlt `DATE-OBS`, wird das ebenfalls gemeldet, statt die Prüfung
still zu überspringen.

Warnungen sind keine Sperre: Wer weiß, dass der optische Aufbau unverändert
war, hakt „Warnungen geprüft" an und übernimmt.

### Dark-Flats am Dateinamen

Erkennungsmuster (Groß-/Kleinschreibung egal, Trenner optional
`_`, `-`, `.`, Leerzeichen):

```
dark[trenner]flat        flat[trenner]dark
```

Umgestuft werden nur Rohframes, deren Header `dark`, `flat`, `bias` oder
`unknown` sagt – ein Light bleibt ein Light. Der vorherige Typ wird gemerkt,
das Abschalten der Regel stellt ihn wieder her. Geprüft wird ausschließlich der
Dateiname, nie der Ordnername.

## 8. Speicherung

Die Zuordnungen landen in der Konfigurationsdatei:

* Linux: `~/.config/siril/custom_amsp.json`
* macOS: `~/Library/Application Support/org.Siril.siril/siril/custom_amsp.json`
* Windows: `%LOCALAPPDATA%\siril\custom_amsp.json`

```json
{
  "strict_assignment": false,
  "assignments": {
    "lights": {
      "M42\u001f2026-03-22\u001fHa\u001f300s": {
        "flat": "subs:flat:2026-03-25:Ha",
        "dark": "subs:dark:*:300s"
      }
    },
    "flats": {
      "2026-03-25\u001fHa": { "bias": "subs:bias:*:" }
    }
  }
}
```

Der Gruppenschlüssel trennt seine Felder mit `\u001f` (ASCII Unit Separator),
damit Objekt- und Filternamen beliebige Zeichen enthalten dürfen.

Zeigt eine gespeicherte Zuordnung auf etwas, das gerade nicht geladen ist,
bleibt sie im Dialog als `⚠ unavailable · …` erhalten und wird nicht still
verworfen.
