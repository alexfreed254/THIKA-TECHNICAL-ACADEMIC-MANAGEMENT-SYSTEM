import { useEffect, useRef } from 'react'
import { io, type Socket } from 'socket.io-client'

/**
 * Socket.IO client — use only for genuine real-time features
 * (biometric live sessions, live dashboards). Ordinary CRUD stays on REST.
 */
export function useSocket(enabled = false) {
  const socketRef = useRef<Socket | null>(null)
  const url = (import.meta.env.VITE_SOCKET_URL as string | undefined) || undefined

  useEffect(() => {
    if (!enabled || !url) return
    const socket = io(url, {
      withCredentials: true,
      autoConnect: true,
      transports: ['websocket', 'polling'],
    })
    socketRef.current = socket
    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [enabled, url])

  return socketRef
}
