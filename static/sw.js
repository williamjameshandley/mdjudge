/* Network-first pass-through; the app is useless stale, so no offline cache. */
self.addEventListener("fetch", () => {});
