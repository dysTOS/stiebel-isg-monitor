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
<http://localhost:8080>. Es werden keine externen Webdienste, CDNs oder JavaScript-Pakete
geladen. Für den Zugriff von anderen Geräten im Heimnetz zusätzlich `--listen 0.0.0.0`
angeben; das Dashboard hat keine Anmeldung und sollte nicht ins Internet freigegeben werden.
Kalendertage werden in der über `STIEBEL_TIMEZONE` konfigurierten Zeitzone ausgewertet;
der Standard ist `Europe/Vienna`.

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
- Jeder Messwert enthält Rohwert, dekodierten Wert und Fehlertext.
- Kommunikationsfehler werden als `connection_events` abgelegt; der Logger läuft weiter und verbindet sich neu.
- Verdichterstarts werden aus einer Flanke `2501 & (1 << 6)` abgeleitet. Beginnt die Beobachtung mitten in einem Lauf, wird dieser als unvollständig markiert.
- Zähler werden als Snapshots gespeichert. Rücksetzungen/Überläufe werden als `counter_events` erkannt, nicht stillschweigend verrechnet.

Historische Starts liefern keinen Verlauf der vergangenen Einzellaufzeiten. Erst die laufende Aufzeichnung kann Takten zuverlässig auswerten.

## Dokumentationsquelle

Stiebel Eltron, *Modbus TCP/IP – Modbus-Systemwerte für Wärmepumpen mit WPM 3(i)*, insbesondere Abschnitte 4.2, 6 sowie Blöcke 1, 3 und 4.
