/* Service Worker — Mon Programme Muscu
   Stratégie :
   - HTML (index) : network-first, on retombe sur le cache si hors-ligne.
     => tu récupères automatiquement les nouvelles versions quand tu as du réseau.
   - Le reste (icônes, manifeste) : cache-first.
   IMPORTANT : les données d'entraînement sont dans localStorage,
   le SW ne les touche jamais. Vider le cache ne perd aucune donnée.
*/

const CACHE = "muscu-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png"
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.addAll(ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (e) {
  const req = e.request;
  if (req.method !== "GET") return;

  const isHTML = req.mode === "navigate" ||
                 (req.headers.get("accept") || "").indexOf("text/html") >= 0;

  if (isHTML) {
    // network-first : toujours la dernière version si le réseau répond
    e.respondWith(
      fetch(req).then(function (res) {
        const copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put("./index.html", copy); });
        return res;
      }).catch(function () {
        return caches.match("./index.html").then(function (r) {
          return r || caches.match("./");
        });
      })
    );
    return;
  }

  // cache-first pour les assets
  e.respondWith(
    caches.match(req).then(function (cached) {
      return cached || fetch(req).then(function (res) {
        const copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      });
    }).catch(function () {
      return caches.match("./index.html");
    })
  );
});

// Permet de forcer la mise à jour depuis la page
self.addEventListener("message", function (e) {
  if (e.data === "SKIP_WAITING") self.skipWaiting();
});
