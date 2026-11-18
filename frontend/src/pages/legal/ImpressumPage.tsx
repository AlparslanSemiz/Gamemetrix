import { CONTROLLER_EMAIL, IMPRESSUM_FULL_URL, LegalPage } from '../../components/LegalPage'

export function ImpressumPage() {
  return (
    <LegalPage lang="de" title="Impressum">
      <h2>Angaben gemäß § 5 DDG</h2>
      <p>Alparslan Semiz</p>
      <p>
        Vollständige Anbieterkennzeichnung:{' '}
        <a href={IMPRESSUM_FULL_URL} rel="noopener">{IMPRESSUM_FULL_URL}</a>
      </p>
      <h2>Kontakt</h2>
      <p>E-Mail: <a href={`mailto:${CONTROLLER_EMAIL}`}>{CONTROLLER_EMAIL}</a></p>
      <h2>Datenschutz</h2>
      <p>
        Siehe die <a href="/datenschutz">Datenschutzerklärung</a>
        {' '}(<a href="/privacy" hrefLang="en" lang="en">English</a>).
      </p>
    </LegalPage>
  )
}
