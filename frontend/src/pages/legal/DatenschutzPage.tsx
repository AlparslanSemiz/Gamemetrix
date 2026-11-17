import { CONTROLLER_EMAIL, IMPRESSUM_FULL_URL, LegalPage } from '../../components/LegalPage'

export function DatenschutzPage() {
  return (
    <LegalPage lang="de" title="Datenschutzerklärung">
      <h2>1. Verantwortlicher</h2>
      <p>
        Alparslan Semiz, siehe <a href="/impressum">Impressum</a> (vollständige Angaben:{' '}
        <a href={IMPRESSUM_FULL_URL} rel="noopener">{IMPRESSUM_FULL_URL}</a>). Kontakt:{' '}
        <a href={`mailto:${CONTROLLER_EMAIL}`}>{CONTROLLER_EMAIL}</a>.
      </p>

      <h2>2. Hosting, Cloudflare und Server-Logs</h2>
      <p>
        GameMetrix läuft auf einem vom Verantwortlichen betriebenen virtuellen Server. Der Datenverkehr
        läuft über Cloudflare, Inc. (USA) als Proxy und CDN. Beim Aufruf einer Seite verarbeiten
        Cloudflare und unser Webserver (nginx) deine IP-Adresse und Anfragedaten (Zeitpunkt, URL,
        Browser, Referrer), um die Seite auszuliefern, sie abzusichern und Fehler zu finden.
        Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO. Für Übermittlungen in die USA gilt das EU-US
        Data Privacy Framework.
      </p>
      <p>
        Ist ein Cloudflare-Web-Analytics-Token konfiguriert, zählt ein kleines Skript von
        static.cloudflareinsights.com Seitenaufrufe ohne Cookies und ohne Profilbildung.
      </p>

      <h2>3. Konto</h2>
      <p>
        Bei der Registrierung speichern wir Anzeigename, E-Mail-Adresse und einen Passwort-Hash (nie das
        Passwort selbst) sowie deine gespeicherten Listen, Alarm-Einstellungen und Sitzungen. Die
        Anmeldung setzt zwei technisch notwendige Cookies (Sitzung und CSRF). Rechtsgrundlage: Art. 6
        Abs. 1 lit. b DSGVO. Du kannst dein Konto auf der Kontoseite löschen; die Daten werden dabei
        entfernt.
      </p>
      <p>
        Wenn du „Continue with Google“ nutzt, übermittelt Google nach der Anmeldung deine bestätigte
        E-Mail-Adresse und deinen Namen. Google verarbeitet Daten nach der eigenen Datenschutzerklärung.
      </p>

      <h2>4. Reichweitenmessung (nur mit Einwilligung)</h2>
      <p>
        Beim ersten Besuch fragen wir nach deiner Entscheidung. Vor einem Klick auf „Allow analytics“
        wird nichts davon erhoben; bei aktiviertem „Do Not Track“ ebenfalls nicht.
      </p>
      <ul>
        <li>
          Eigene Seitenaufruf- und Ereignis-API: Pfad, Referrer, Seitentitel, Bildschirmgröße, Sprache,
          Zeitzone, eine anonyme Besucher-ID in deinem Browser (localStorage) und eine Sitzungs-ID
          (sessionStorage). Deine IP-Adresse wird auf einen Hash reduziert; die rohe IP-Adresse und der
          User-Agent werden standardmäßig nicht gespeichert und, falls das je aktiviert wird, nach 30 Tagen gelöscht.
        </li>
        <li>
          Google Analytics, falls konfiguriert (Google Ireland Ltd. / Google LLC): gleichartige
          Messdaten, Werbepersonalisierung und Google Signals sind deaktiviert.
        </li>
      </ul>
      <p>
        Rechtsgrundlage: Art. 6 Abs. 1 lit. a DSGVO und § 25 Abs. 1 TDDDG. Du kannst die Einwilligung
        jederzeit unter <a href="/settings">Settings</a> widerrufen.
      </p>

      <h2>5. Lokaler Speicher im Browser</h2>
      <p>
        Ohne Einwilligung speichern wir nur, was die Seite zum Funktionieren braucht: Listen- und
        Ansichtseinstellungen, gespeicherte Listen (ohne Anmeldung), deine Analytics-Entscheidung und einen
        Katalog-Schnappschuss für schnelleres Zurücknavigieren. Diese Daten bleiben auf deinem Gerät
        (§ 25 Abs. 2 TDDDG).
      </p>

      <h2>6. Bilder und Videos anderer Anbieter</h2>
      <p>
        Spielcover und Screenshots werden direkt von media.rawg.io (RAWG), dem Steam-CDN (Akamai) und
        CheapShark geladen. Dein Browser übermittelt dabei IP-Adresse und Browserdaten an diese Anbieter.
        Trailer werden im datenschutzfreundlichen Modus von YouTube (youtube-nocookie.com) eingebunden und
        erst geladen, wenn du einen Trailer öffnest; YouTube (Google) erhält dann deine IP-Adresse.
        Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO.
      </p>

      <h2>7. Speicherdauer</h2>
      <p>
        Kontodaten bleiben bis zur Löschung deines Kontos gespeichert. Sitzungen laufen automatisch ab. Rohe
        IP-Daten von Analytics-Ereignissen (standardmäßig aus) werden nach 30 Tagen gelöscht; Server-Logs werden regelmäßig
        rotiert.
      </p>

      <h2>8. Deine Rechte</h2>
      <p>
        Du hast das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit und
        Widerspruch (Art. 15-21 DSGVO) sowie auf Widerruf einer Einwilligung. Schreib dazu an{' '}
        <a href={`mailto:${CONTROLLER_EMAIL}`}>{CONTROLLER_EMAIL}</a>. Außerdem kannst du dich bei der
        Aufsichtsbehörde beschweren: Der Landesbeauftragte für den Datenschutz und die
        Informationsfreiheit Baden-Württemberg (LfDI), Stuttgart.
      </p>

      <p className="legal-lang">
        <a href="/privacy" hrefLang="en" lang="en">English version</a>
        {' · '}
        <a href="/impressum">Impressum</a>
      </p>
    </LegalPage>
  )
}
