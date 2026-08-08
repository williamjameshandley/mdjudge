# Maintainer: Will Handley <wh260@cam.ac.uk>
pkgbase=mdjudge
pkgname=(mdjudge mdjudge-client)
pkgver=$(grep '^version = ' pyproject.toml | head -1 | sed 's/.*= "\(.*\)"/\1/')
pkgrel=1
pkgdesc='mdjudge: the judgement queue PWA and API over an mddb deck'
arch=('any')
url='https://github.com/williamjameshandley/mdjudge'
license=('MIT')
depends=('python' 'python-mddb>=0.0.27' 'python-alan-pwa' 'nginx' 'git')


package_mdjudge() {
  install=mdjudge.install
  depends=('python' 'python-mddb>=0.0.27' 'python-alan-pwa' 'nginx' 'git' 'mdjudge-client')
  cd "$startdir"
  cd "$startdir"
  install -Dm644 app.py "$pkgdir/usr/lib/mdjudge/app.py"
  for f in static/*; do
    install -Dm644 "$f" "$pkgdir/usr/lib/mdjudge/static/$(basename "$f")"
  done
  install -Dm755 mdjudge-init "$pkgdir/usr/lib/mdjudge/mdjudge-init"
  install -Dm644 mdjudge.service "$pkgdir/usr/lib/systemd/system/mdjudge.service"
  install -Dm644 mdjudge.sysusers.conf "$pkgdir/usr/lib/sysusers.d/mdjudge.conf"
  install -Dm644 mdjudge.tmpfiles.conf "$pkgdir/usr/lib/tmpfiles.d/mdjudge.conf"
  install -Dm644 mdjudge.nginx.conf "$pkgdir/etc/nginx/lovelace.d/mdjudge.conf"
}

package_mdjudge-client() {
  pkgdesc='mdjudge: the judgement vocabulary and the composable HTTP client'
  depends=('python')
  install=""
  cd "$startdir"
  local purelib
  purelib=$(env -u VIRTUAL_ENV PATH=/usr/bin:/bin \
    python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
  install -Dm644 src/mdjudge/__init__.py "$pkgdir/$purelib/mdjudge/__init__.py"
  install -Dm644 src/mdjudge/_core.py    "$pkgdir/$purelib/mdjudge/_core.py"
  install -Dm644 src/mdjudge/client.py   "$pkgdir/$purelib/mdjudge/client.py"
}
