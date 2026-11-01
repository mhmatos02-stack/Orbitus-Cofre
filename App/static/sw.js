/* Orbitus — service worker: só recebe avisos (push) e abre o painel no toque. Não guarda nada em cache. */
self.addEventListener('install', function (e) { self.skipWaiting() });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()) });
self.addEventListener('push', function (e) {
  var d = {}; try { d = e.data ? e.data.json() : {} } catch (x) { d = { titulo: 'Orbitus', corpo: e.data ? e.data.text() : '' } }
  e.waitUntil(self.registration.showNotification(d.titulo || 'Orbitus', {
    body: d.corpo || '', tag: d.tag || 'orbitus', renotify: true, icon: '/static/icone-192.png', badge: '/static/icone-192.png', data: { url: d.url || '/' }
  }));
});
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (cs) {
    for (var i = 0; i < cs.length; i++) { if ('focus' in cs[i]) { cs[i].navigate && cs[i].navigate(url); return cs[i].focus() } }
    return self.clients.openWindow(url);
  }));
});
