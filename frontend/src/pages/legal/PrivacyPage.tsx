import { CONTROLLER_EMAIL, IMPRESSUM_FULL_URL, LegalPage } from '../../components/LegalPage'

export function PrivacyPage() {
  return (
    <LegalPage title="Privacy policy">
      <h2>1. Controller</h2>
      <p>
        Alparslan Semiz, see the <a href="/impressum">Impressum</a> (full details:{' '}
        <a href={IMPRESSUM_FULL_URL} rel="noopener">{IMPRESSUM_FULL_URL}</a>). Contact:{' '}
        <a href={`mailto:${CONTROLLER_EMAIL}`}>{CONTROLLER_EMAIL}</a>.
      </p>

      <h2>2. Hosting, Cloudflare and server logs</h2>
      <p>
        GameMetrix runs on a virtual server operated by the controller. Traffic passes through
        Cloudflare, Inc. (USA) as a proxy and CDN. When you open a page, Cloudflare and our web
        server (nginx) process your IP address and request data (time, URL, browser, referrer) to
        deliver the page, keep it secure and find errors. Legal basis: Art. 6(1)(f) GDPR.
        Transfers to the USA rely on the EU-US Data Privacy Framework.
      </p>
      <p>
        If a Cloudflare Web Analytics token is configured, a small script from
        static.cloudflareinsights.com counts page views without cookies and without profiles.
      </p>

      <h2>3. Account</h2>
      <p>
        If you register, we store your display name, e-mail address and a password hash (never the
        password itself), plus your saved lists, alert preferences and sessions. Signing in sets
        two strictly necessary cookies (a session cookie and a CSRF cookie). Legal basis: Art.
        6(1)(b) GDPR. You can delete your account in the account page, which removes this data.
      </p>
      <p>
        If you choose &quot;Continue with Google&quot;, Google sends us your verified e-mail address and
        name after you sign in. Google processes your data under its own privacy policy.
      </p>

      <h2>4. Analytics (only with your consent)</h2>
      <p>
        On your first visit we ask for a choice. Nothing below is collected before you click
        &quot;Allow analytics&quot;, and nothing is collected if your browser sends Do Not Track.
      </p>
      <ul>
        <li>
          Our own page-view and event API: path, referrer, page title, screen size, language,
          time zone, an anonymous visitor ID stored in your browser (localStorage) and a session ID
          (sessionStorage). Your IP address is reduced to a hash; the raw IP address and user
          agent are not stored by default, and if that is ever enabled they are deleted after 30 days.
        </li>
        <li>
          Google Analytics, if configured (Google Ireland Ltd. / Google LLC): the same kind of
          measurement data, with advertising personalization and Google signals disabled.
        </li>
      </ul>
      <p>
        Legal basis: Art. 6(1)(a) GDPR and § 25(1) TDDDG. You can withdraw consent at any time in{' '}
        <a href="/settings">Settings</a>.
      </p>

      <h2>5. Local storage in your browser</h2>
      <p>
        Without consent we only store what the site needs to work: your list and view settings,
        saved lists (when not signed in), your analytics choice and a catalog snapshot for faster
        back navigation. These stay on your device (§ 25(2) TDDDG).
      </p>

      <h2>6. Images and videos from other providers</h2>
      <p>
        Game covers and screenshots are loaded directly from media.rawg.io (RAWG), the Steam CDN
        (Akamai) and CheapShark. Your browser therefore sends your IP address and browser data to
        these providers. Trailers are embedded from YouTube in privacy-enhanced mode
        (youtube-nocookie.com) and load only after you open a trailer; YouTube (Google) then
        receives your IP address. Legal basis: Art. 6(1)(f) GDPR.
      </p>

      <h2>7. Retention</h2>
      <p>
        Account data is kept until you delete your account. Sessions expire automatically. Raw IP
        records of analytics events (off by default) are deleted after 30 days; server logs are rotated regularly.
      </p>

      <h2>8. Your rights</h2>
      <p>
        You have the right to access, rectification, erasure, restriction, data portability and
        objection (Art. 15-21 GDPR), and to withdraw consent at any time. Please write to{' '}
        <a href={`mailto:${CONTROLLER_EMAIL}`}>{CONTROLLER_EMAIL}</a>. You can also lodge a
        complaint with the supervisory authority: Der Landesbeauftragte für den Datenschutz und
        die Informationsfreiheit Baden-Württemberg (LfDI), Stuttgart.
      </p>

      <p className="legal-lang">
        <a href="/datenschutz" hrefLang="de" lang="de">Deutsche Fassung</a>
        {' · '}
        <a href="/impressum">Impressum</a>
      </p>
    </LegalPage>
  )
}
