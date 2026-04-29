/**
 * Result<T, E> — Rust-inspired sum type for operations that may fail.
 *
 * Use this in service methods that have predictable failure modes.
 * Forces callers to handle both cases explicitly.
 *
 * @example
 *   const result = await tryFetchUser(id)
 *   if (result.ok) {
 *     console.log(result.value)  // User
 *   } else {
 *     console.log(result.error)  // Error
 *   }
 */

export type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E }

export function Ok<T>(value: T): Result<T, never> {
  return { ok: true, value }
}

export function Err<E>(error: E): Result<never, E> {
  return { ok: false, error }
}

export function isOk<T, E>(result: Result<T, E>): result is { ok: true; value: T } {
  return result.ok
}

export function isErr<T, E>(result: Result<T, E>): result is { ok: false; error: E } {
  return !result.ok
}

/**
 * Wrap a promise-returning function, converting thrown errors to Results.
 */
export async function tryAsync<T>(fn: () => Promise<T>): Promise<Result<T, Error>> {
  try {
    const value = await fn()
    return Ok(value)
  } catch (error) {
    return Err(error instanceof Error ? error : new Error(String(error)))
  }
}

/**
 * Wrap a synchronous function, converting thrown errors to Results.
 */
export function trySync<T>(fn: () => T): Result<T, Error> {
  try {
    return Ok(fn())
  } catch (error) {
    return Err(error instanceof Error ? error : new Error(String(error)))
  }
}
