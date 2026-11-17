import './SiteLegalFooter.css'

// Every route gets Impressum and Privacy links. The catalog shell has its own
// footer that already carries them, so this one hides itself there (see CSS).
export function SiteLegalFooter() {
  return (
    <footer className="site-legal-footer">
      <nav aria-label="Legal">
        <a href="/impressum">Impressum</a>
        <a href="/privacy">Privacy</a>
      </nav>
    </footer>
  )
}
