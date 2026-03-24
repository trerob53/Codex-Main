/* Cerasus Hub — Client JS v3 */

// Password visibility toggle
function togglePassword(btn) {
  const input = btn.parentElement.querySelector('input');
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '\u{1F441}';
  } else {
    input.type = 'password';
    btn.textContent = '\u{1F441}\u{200D}\u{1F5E8}';
  }
}

// Dark mode toggle
function toggleDarkMode() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', isDark ? 'light' : 'dark');
  fetch('/api/toggle-dark', { method: 'POST' });
}

// Notification dropdown
function toggleNotifications(event) {
  event.stopPropagation();
  const dd = document.getElementById('notification-dropdown');
  if (dd) dd.classList.toggle('open');
  const um = document.getElementById('user-dropdown');
  if (um) um.classList.remove('open');
}

// User menu dropdown
function toggleUserMenu(event) {
  event.stopPropagation();
  const dd = document.getElementById('user-dropdown');
  if (dd) dd.classList.toggle('open');
  const nd = document.getElementById('notification-dropdown');
  if (nd) nd.classList.remove('open');
}

// Close dropdowns on outside click
document.addEventListener('click', function() {
  document.querySelectorAll('.notification-dropdown.open, .user-dropdown.open').forEach(function(el) {
    el.classList.remove('open');
  });
  // Close shortcuts overlay on outside click
  var so = document.getElementById('shortcuts-overlay');
  if (so) so.remove();
});

// Mobile hamburger
function toggleMobileNav() {
  const links = document.querySelector('.nav-links');
  if (links) links.classList.toggle('open');
}

// ── Toast notifications (auto-dismiss) ──────────────
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.toast').forEach(function(el) {
    setTimeout(function() {
      el.style.opacity = '0';
      el.style.transform = 'translateX(40px)';
      setTimeout(function() { el.remove(); }, 300);
    }, 5000);
  });
});

// Update date display
function updateDateDisplay() {
  const el = document.getElementById('nav-date');
  if (!el) return;
  const now = new Date();
  const opts = { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' };
  el.textContent = now.toLocaleDateString('en-US', opts);
}
document.addEventListener('DOMContentLoaded', updateDateDisplay);

// Search debounce
let searchTimer = null;
function debounceSearch(input, targetId, url) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function() {
    const q = input.value.trim();
    const target = document.getElementById(targetId);
    if (q.length < 2) {
      target.innerHTML = '';
      target.style.display = 'none';
      return;
    }
    fetch(url + '?q=' + encodeURIComponent(q))
      .then(function(r) { return r.text(); })
      .then(function(html) {
        target.innerHTML = html;
        target.style.display = html.trim() ? 'block' : 'none';
      });
  }, 300);
}

// HTMX page transition
document.addEventListener('htmx:afterSwap', function() {
  updateDateDisplay();
});

// ── Dashboard KPI auto-refresh (60s) ────────────────
document.addEventListener('DOMContentLoaded', function() {
  var kpiContainer = document.getElementById('dashboard-kpis');
  if (kpiContainer) {
    setInterval(function() {
      fetch('/api/dashboard')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var map = {
            'kpi-officers': data.officers,
            'kpi-reviews': data.pending_reviews,
            'kpi-lowstock': data.low_stock,
            'kpi-requests': data.open_requests
          };
          for (var id in map) {
            var el = document.getElementById(id);
            if (el) el.textContent = map[id];
          }
        }).catch(function() {});
    }, 60000);
  }
});

// ── Keyboard shortcuts overlay ──────────────────────
document.addEventListener('keydown', function(e) {
  // ? key (shift+/) shows shortcuts
  if (e.key === '?' && !e.ctrlKey && !e.altKey) {
    // Don't trigger if typing in an input/textarea
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    e.preventDefault();
    toggleShortcutsOverlay();
  }
  // Escape closes overlay
  if (e.key === 'Escape') {
    var so = document.getElementById('shortcuts-overlay');
    if (so) so.remove();
  }
});

function toggleShortcutsOverlay() {
  var existing = document.getElementById('shortcuts-overlay');
  if (existing) { existing.remove(); return; }

  var shortcuts = [
    ['?', 'Show this help'],
    ['Esc', 'Close overlay'],
    ['D', 'Toggle dark mode (click button)'],
  ];

  var html = '<div class="shortcuts-overlay" id="shortcuts-overlay" onclick="if(event.target===this)this.remove()">';
  html += '<div class="shortcuts-card" onclick="event.stopPropagation()">';
  html += '<h2>Keyboard Shortcuts</h2>';
  shortcuts.forEach(function(s) {
    html += '<div class="shortcut-row"><span style="color:var(--text-light)">' + s[1] + '</span><span class="shortcut-key">' + s[0] + '</span></div>';
  });
  html += '<div style="margin-top:16px;text-align:center;font-size:12px;color:var(--text-light);">Press <span class="shortcut-key">Esc</span> to close</div>';
  html += '</div></div>';

  document.body.insertAdjacentHTML('beforeend', html);
}

// ── Who's online detail toggle ──────────────────────
function toggleOnlineDetail() {
  var el = document.getElementById('online-detail');
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ── Track last module for redirect after login ──────
document.addEventListener('DOMContentLoaded', function() {
  var path = window.location.pathname;
  if (path.indexOf('/module/') === 0) {
    var module = path.split('/')[2];
    if (module) {
      fetch('/api/set-last-module', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: module })
      }).catch(function() {});
    }
  }
});
