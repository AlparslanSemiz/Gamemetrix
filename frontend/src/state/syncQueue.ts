// Collection toggles are fire-and-forget network calls. Two quick taps on the
// same game and list (add, then remove) must reach the server in that order, or
// the slower request can land last and leave the account disagreeing with the
// device. Calls for one key run strictly one after another; different keys stay
// concurrent.
const tails = new Map<string, Promise<unknown>>()

export function enqueueSync<T>(key: string, task: () => Promise<T>): Promise<T> {
  const previous = tails.get(key) ?? Promise.resolve()
  const run = previous.then(task, task)
  const tail = run.catch(() => undefined)
  tails.set(key, tail)
  void tail.then(() => {
    if (tails.get(key) === tail) tails.delete(key)
  })
  return run
}
