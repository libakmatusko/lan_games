# Design decisions

## Initial implementation

- The default lobby target is the game's maximum player count. `--players`
  selects a smaller supported target. A game starts only after every seat is
  connected and ready.
- A disconnected seat retains its opaque session token for 60 seconds. An
  explicit `bye` releases the seat immediately; unexpected disconnects retain
  it for reconnection. The client stores its token with the last connection
  settings so a restarted client can resume while the token remains valid.
- Invalid game actions are rejected without disconnecting the client. Malformed
  frames and unsupported protocol messages close only the offending connection.
- Terminal UIs run off the asyncio event loop. The client stays responsive to
  network updates while a player is entering a command.
- Real-time games receive fixed-rate server ticks and publish per-player views
  after each tick. Game logic remains independent of networking and UI.
- A completed match ends its session; rematches and lobby reuse are deferred
  rather than expanding this first version into Phase 9 features.
