# SAMS Club Lounge – Compliance Delivery Index

**Stand:** 06.08.2026  
**Zweck:** Zentraler Übergabepunkt für Geschäftsführung, Rechtsanwalt, Datenschutzberatung, Steuerberatung und technische Prüfung.

## 1. Technische Nachweise

| Bereich | Nachweis im Repository | Status |
|---|---|---|
| Architektur und Datenflüsse | `COMPLIANCE-SECURITY-ARCHITECTURE-DE.md` | technisch dokumentiert |
| Technische/organisatorische Maßnahmen | `TOM-DE.md` | Entwurf zur organisatorischen Freigabe |
| Rollen und MFA | Code in `cards/security_*` und Tests | implementiert, Production-Rollout nach Secret/Deploy |
| Audit-Integrität | `AuditChainSeal`, `verify_audit_chain`, Tests | implementiert |
| Finanzdaten-Unveränderlichkeit | Compliance Guards und Gegenbuchungsprinzip | implementiert |
| sicherer Zahlungs-QR | signierter kurzlebiger Token | implementiert |
| Backup und Restore | `ops/backup/` und STRATO Workflow | vorbereitet; echter Lauf nach Merge erforderlich |
| Server-Hardening | `ops/security/harden-strato.sh` | vorbereitet; manueller Production-Lauf erforderlich |
| Dependency Security | Security Audit + Dependabot | vorbereitet/CI |
| Incident Response | `INCIDENT-RESPONSE-RUNBOOK-DE.md` | Entwurf, Kontakte offen |

## 2. Datenschutz-Unterlagen

- `LAWYER-DATA-PROTECTION-REVIEW-PACK-DE.md`
- `VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN-DE.md`
- `TOM-DE.md`
- `RETENTION-MATRIX-DE.md`
- `INCIDENT-RESPONSE-RUNBOOK-DE.md`

## 3. Steuer-/Kassen-Unterlagen

- `TAX-WALLET-REVIEW-PACK-DE.md`
- technische Ledger-/Auditbeschreibung in `COMPLIANCE-SECURITY-ARCHITECTURE-DE.md`

## 4. Zahlungsaufsichtsrecht

- `ZAG-LIMITED-NETWORK-REVIEW-PACK-DE.md`

Eine Ausnahme oder Erlaubnisfreiheit wird nicht behauptet. Ergebnis und Auflagen müssen schriftlich durch fachkundige Beratung festgehalten werden.

## 5. Noch benötigte Betreiberangaben

1. vollständige Firma und Anschrift des datenschutzrechtlich Verantwortlichen;
2. juristische Person, die das Guthaben ausgibt und Kundengeld entgegennimmt;
3. Betreiberfirma und Anschrift jedes Standorts;
4. Geschäftsführung und Datenschutzkontakt;
5. Datenschutzbeauftragter oder dokumentierte Entscheidung, warum keiner bestellt ist;
6. zuständige Datenschutzaufsichtsbehörde;
7. eingesetzte Registrierkasse, TSE und Kassenanbieter;
8. Liste der mit Guthaben erwerbbaren Waren/Dienstleistungen und Steuersätze;
9. vorgesehene Saldo-, Auflade-, Tages- und Monatslimits;
10. Rechts-/Steuerberater und Eskalationskontakte für Incidents.

## 6. Noch benötigte technische Aktionen

- Repository Secret `MFA_ENCRYPTION_KEY` mit mindestens 32 zufälligen Zeichen erstellen.
- Repository von `public` auf `private` umstellen.
- PR nach vollständig grüner CI mergen.
- erfolgreichen STRATO-Deploy abwarten.
- Workflow **Harden STRATO Security** einmal kontrolliert ausführen.
- Workflow **Configure Production Backups** ausführen und erfolgreichen Restore-Drill nachweisen.
- erster Owner und jeder Manager richtet TOTP-2FA ein und sichert Recovery Codes offline.
- Rollenliste prüfen und nicht mehr benötigte Zugänge deaktivieren.

## 7. Freigabegates vor endgültigem Wallet-Rollout

| Gate | Erforderlicher Nachweis | Freigegeben von |
|---|---|---|
| Datenschutz | finale Datenschutzerklärung, AVV, VVT, TOM, Fristen | Verantwortlicher + Rechts/DSB |
| Steuer/Gutschein | schriftliche Einordnung und Kontierung | Steuerberater |
| ZAG | schriftliche Einordnung/Anzeigeentscheidung | Fachanwalt/Compliance |
| Kasse | POS/TSE/DSFinV-K-Prozess | Steuerberater + Kassenanbieter |
| Betrieb | Backup, Restore, Hardening, MFA, Incident-Kontakte | Technische Leitung + Betreiber |

## 8. Abschluss

Die technische Umsetzung reduziert wesentliche Risiken und erzeugt prüfbare Nachweise. Rechtliche und steuerliche Freigaben bleiben Entscheidungen der dafür zuständigen Berater und des Betreibers.
