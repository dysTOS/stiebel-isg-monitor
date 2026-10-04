# Stiebel ISG Monitor

Lokaler, **read-only** Modbus-TCP-Logger für ein Stiebel-Eltron-ISG/WPM.

## Schnellstart

```bash
python3 -m stiebel_monitor discover --subnet 192.168.0.0/24
cp .env.example .env
# STIEBEL_ISG_HOST in .env eintragen
python3 -m stiebel_monitor probe
python3 -m stiebel_monitor serve
```

Der letzte Befehl startet gleichzeitig das Monitoring und das lokale Dashboard unter
<http://localhost:8081>. Es werden keine externen Webdienste, CDNs oder JavaScript-Pakete
geladen. Für den Zugriff von anderen Geräten im Heimnetz zusätzlich `--listen 0.0.0.0`
angeben; das Dashboard hat keine Anmeldung und sollte nicht ins Internet freigegeben werden.
Kalendertage werden in der über `STIEBEL_TIMEZONE` konfigurierten Zeitzone ausgewertet;
der Standard ist `Europe/Vienna`.

## Progressive Web App

Das Dashboard lässt sich über den Browser als App installieren. Es speichert die App-Oberfläche
und den zuletzt geladenen Dashboard-Snapshot für die Offline-Ansicht. Live-Registerabfragen
sowie Datenbank-Import und -Export benötigen weiterhin eine Verbindung zum Server. Auf demselben
Gerät funktioniert die Installation unter `http://localhost:8081`; für den Zugriff und die
Installation von anderen Geräten ist HTTPS erforderlich.

## Docker

Docker Compose startet Dashboard und Logger gemeinsam. Lege zuerst die Konfiguration an
und trage die IP-Adresse des ISG ein:

```bash
cp .env.example .env
# STIEBEL_ISG_HOST in .env eintragen
docker compose up -d --build
```

Das Dashboard ist danach unter <http://localhost:8081> erreichbar. Die SQLite-Datenbank
liegt in einem verwalteten Volume und bleibt bei Container-Neuerstellung und Updates
erhalten. `docker compose down` entfernt den Container, aber nicht das Daten-Volume;
`docker compose down -v` löscht auch die gespeicherten Messdaten.

Im eingeklappten Bereich **Daten sichern / wiederherstellen** im Seitenfuß kannst du eine
vollständige SQLite-Sicherung herunterladen oder importieren. Der Import prüft die Datei
und ersetzt anschließend alle gespeicherten Daten; vor dem Start erscheint eine
Bestätigungswarnung. Uploads sind auf 512 MB begrenzt.

Über den Button **Register** öffnet sich eine Diagnoseansicht. Sie liest die bekannten
Register erst beim Aufruf aus, kennzeichnet das jeweilige WPM-Profil und hält das Ergebnis
zehn Sekunden im Cache, damit parallele Browseraufrufe das ISG nicht unnötig belasten.

Nur den Logger ohne Weboberfläche starten:

```bash
python3 -m stiebel_monitor log
```

Die IP-Adresse wird nicht geraten: zuerst im Router/DHCP-Client-Verzeichnis oder in der ISG-Servicewelt prüfen. `discover` versucht nur TCP/502-Verbindungen im angegebenen privaten Netz. Das Programm schreibt keine Modbus-Register; es gibt bewusst keine Schreibfunktion.

## Register und Adressierung

Die Werte in `registers.py` sind die 1-basierten Adressen aus der offiziellen Stiebel-Eltron-Modbus-Dokumentation. Der Client konvertiert sie intern zu 0-basierten PDU-Adressen. Temperaturwerte werden mit 0,1 °C skaliert; die Dokumentation ist maßgeblich, wenn ein Gerät eine andere Codierung meldet. `32768` wird als `None` gespeichert, der Rohwert bleibt erhalten.

Die Dokumentation nennt für das klassische ISG web/plus eine Modbus-Softwareerweiterung. Ob das konkrete Gerät (einschließlich ISG Connect) kompatibel ist, muss am Typenschild/der Servicewelt und durch den Porttest geprüft werden.

## Sicherheit und Datenqualität

- UTC-Zeitstempel (`timestamp_utc`) und lokale Laufzeitdiagnosen werden in SQLite gespeichert.
- Historisch gespeichert werden die Dashboard-Verläufe, die Betriebszustände und die dafür angezeigten Zähler. Die übrigen Register liest die Diagnoseansicht bei Bedarf frisch aus.
- Rohwerte für nicht verfügbare Register (`32768`) und wiederholte Lesefehler werden nur gespeichert, wenn sich der Zustand ändert.
- Kommunikationsfehler werden als `connection_events` abgelegt; der Logger läuft weiter und verbindet sich neu.
- Verdichterstarts werden ausschließlich aus einer Flanke `2501 & (1 << 6)` abgeleitet. Direkte Wechsel zwischen Warmwasser und Heizen werden als Phasen innerhalb desselben Verdichterlaufs gespeichert. Beginnt die Beobachtung mitten in einem Lauf oder liegt zwischen zwei Statuswerten eine längere Messlücke, werden die betroffenen Daten als unvollständig markiert, ohne einen zusätzlichen Start anzunehmen.
- Zähler werden als Snapshots gespeichert. Rücksetzungen/Überläufe werden als `counter_events` erkannt, nicht stillschweigend verrechnet.

Historische Starts liefern keinen Verlauf der vergangenen Einzellaufzeiten. Erst die laufende Aufzeichnung kann Takten zuverlässig auswerten.

## Dokumentationsquelle

Stiebel Eltron, *Modbus TCP/IP – Modbus-Systemwerte für Wärmepumpen mit WPM 3(i)*, insbesondere Abschnitte 4.2, 6 sowie Blöcke 1, 3 und 4.
