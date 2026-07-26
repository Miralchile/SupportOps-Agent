import { proxy, subscribe } from 'valtio'

const STORAGE_KEY = 'supportops.user'

/** Minimal localStorage persistence for a valtio proxy state. */
function proxyWithStorage<T extends object>(key: string, initialState: T): T {
  let saved: Partial<T> = {}
  try {
    saved = JSON.parse(window.localStorage.getItem(key) || '{}')
  } catch {
    saved = {}
  }
  const state = proxy({ ...initialState, ...saved })
  subscribe(state, () => {
    try {
      window.localStorage.setItem(key, JSON.stringify(state))
    } catch {
      // storage may be unavailable (private mode / quota); state stays in memory
    }
  })
  return state
}

const state = proxyWithStorage(STORAGE_KEY, {
  token: null as string | null,
  username: null as string | null,
})

const actions = {
  setToken(token: string) {
    state.token = token
  },
  setUsername(username: string) {
    state.username = username
  },
}

export const userState = state
export const userActions = actions
