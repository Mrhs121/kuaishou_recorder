export interface RoomStatus {
  id: string
  url: string
  anchor_name: string
  quality: string
  is_live: boolean
  is_recording: boolean
  status: 'idle' | 'live' | 'recording' | 'error' | 'disabled'
  file_path: string | null
  error_message: string | null
  record_started_at: string | null
}

export interface RoomCreate {
  url: string
  quality?: string
  browser?: string
}

export interface Settings {
  save_path: string
  save_format: string
  default_quality: string
  browser_for_cookies: string
  cookies: string
  proxy: string
  poll_interval: number
}
