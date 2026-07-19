import { useEffect, useState } from 'react'
import { getScoreWeights, recalculateScores, updateScoreWeights } from '../services/games'

export function ScoreWeightSettings({ token, onSaved }: { token: string; onSaved: () => void }) {
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [message, setMessage] = useState<string>('Loading score weights...')

  useEffect(() => {
    void getScoreWeights()
      .then((response) => {
        setWeights(response.weights)
        setMessage('Tune how strongly each source contributes to Metrix Score.')
      })
      .catch(() => setMessage('Score weights could not be loaded.'))
  }, [])

  const saveWeights = async () => {
    setMessage('Saving weights and recalculating scores...')
    try {
      await updateScoreWeights(weights, token)
      const result = await recalculateScores(token)
      setMessage(`Saved. Recalculated ${result.recalculated} games.`)
      onSaved()
    } catch {
      setMessage('Weights could not be saved.')
    }
  }

  return (
    <div className="score-weight-panel">
      <p>{message}</p>
      <div className="weight-grid">
        {Object.entries(weights).map(([source, value]) => (
          <label key={source}>
            <span>{source}</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={value}
              onChange={(event) =>
                setWeights((current) => ({
                  ...current,
                  [source]: Number(event.target.value),
                }))
              }
            />
            <output>{value.toFixed(2)}</output>
          </label>
        ))}
      </div>
      <button type="button" className="apply-button settings-save" onClick={saveWeights}>
        Save weights
      </button>
    </div>
  )
}
