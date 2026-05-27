import type { RoomCreate, RoomStatus, Settings } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const rsp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!rsp.ok) {
    const body = await rsp.json().catch(() => ({}))
    throw new Error(body.detail || rsp.statusText)
  }
  return rsp.json()
}

// Rooms
export const getRooms = () => request<RoomStatus[]>('/rooms')
export const addRoom = (data: RoomCreate) =>
  request<Record<string, unknown>>('/rooms', { method: 'POST', body: JSON.stringify(data) })
export const deleteRoom = (id: string) =>
  request<Record<string, unknown>>(`/rooms/${id}`, { method: 'DELETE' })
export const startRoom = (id: string) =>
  request<RoomStatus>(`/rooms/${id}/start`, { method: 'POST' })
export const stopRoom = (id: string) =>
  request<RoomStatus>(`/rooms/${id}/stop`, { method: 'POST' })

// Settings
export const getSettings = () => request<Settings>('/settings')
export const updateSettings = (data: Settings) =>
  request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(data) })
