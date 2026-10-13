type TokenStorage = Pick<Storage, "getItem" | "setItem">;

export function createSessionTokenStore(storage: () => TokenStorage) {
  let current = "";
  let loaded = false;
  return {
    read(): string {
      if (!loaded) {
        loaded = true;
        try { current = storage().getItem("drift_token") || ""; } catch { /* Use page memory when storage is denied. */ }
      }
      return current;
    },
    write(value: string): boolean {
      loaded = true;
      current = value;
      try { storage().setItem("drift_token", value); return true; } catch { return false; }
    },
  };
}
