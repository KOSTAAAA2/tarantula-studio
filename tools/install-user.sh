#!/usr/bin/env bash
# Install Tarantula Studio for the current user:
#   * desktop entry + icon under ~/.local/share
#   * launcher in ~/.local/bin that points at this source tree
# The udev rule is NOT installed automatically; use the app's Diagnostics page
# (pkexec) or run the sudo command printed at the end.
set -euo pipefail

project="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
bindir="${HOME}/.local/bin"
appdir="${HOME}/.local/share/applications"
icondir="${HOME}/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$bindir" "$appdir" "$icondir"

cat > "$bindir/tarantula-studio" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$project"
exec python3 -m tarantula_studio "\$@"
EOF
chmod 755 "$bindir/tarantula-studio"

install -m 644 "$project/assets/tarantula-studio.svg" "$icondir/tarantula-studio.svg"
install -m 644 "$project/tarantula-studio.desktop" "$appdir/tarantula-studio.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$appdir" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed:"
echo "  $bindir/tarantula-studio"
echo "  $appdir/tarantula-studio.desktop"
echo "  $icondir/tarantula-studio.svg"
echo
echo "Make sure ~/.local/bin is in PATH, then launch 'tarantula-studio'."
echo "Install the udev rule from the app's Diagnostics page, or run:"
echo "  sudo install -m 644 '$project/udev/70-gamesir-tarantula.rules' /etc/udev/rules.d/"
echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
