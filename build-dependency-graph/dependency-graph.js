/* Prerequisite and postrequisite graphs of definitions and results.
   Reads dependency-graph.json (tools/build_dependency_graph.py): an edge [A, B]
   means A uses B, so B is a prerequisite of A.  No library: plain SVG.
   - Under every #def-/#thm-/#lem-/#prp-/#cor- div, a folded "Dependencies" graph
     of its prerequisites (left) and postrequisites (right), DEPTH levels each way.
   - In any element with id "dependency-graph-page", the whole page's graph. */
(function () {
  "use strict";
  var DEPTH = 2, NS = "http://www.w3.org/2000/svg", W = 190, H = 34, GX = 60, GY = 12;
  var script = document.currentScript;
  var base = script ? script.src.replace(/[^/]*$/, "") : "";
  var page = location.pathname.split("/").pop().replace(/\.html$/, "");

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function href(n, g) {
    if (n.url) return n.url;
    if (n.site !== g.site) return "https://morrison-lab.github.io/" + n.site + "/" + n.page + ".html#" + n.div;
    return (n.page === page ? "" : n.page + ".html") + "#" + n.div;
  }
  function clip(s) { return s.length > 28 ? s.slice(0, 27) + "\u2026" : s; }

  /* Draw `levels` (array of arrays of nodes) with `edges` ([prereq, dependent] key pairs). */
  function draw(levels, edges, focus, g) {
    var rows = Math.max.apply(null, levels.map(function (l) { return l.length; }).concat(1));
    var w = levels.length * (W + GX) - GX, h = rows * (H + GY) - GY;
    var uid = "dg-arrow-" + (draw.n = (draw.n || 0) + 1);
    var svg = el("svg", { viewBox: "0 0 " + w + " " + h, width: Math.min(w, 1400), role: "img",
      "aria-label": "Prerequisite graph" }), pos = {};
    var defs = el("defs", {}, svg);
    var mk = el("marker", { id: uid, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6,
      markerHeight: 6, orient: "auto-start-reverse" }, defs);
    el("path", { d: "M0 0L10 5L0 10z", fill: "#888" }, mk);
    levels.forEach(function (l, i) {
      var off = (h - (l.length * (H + GY) - GY)) / 2;
      l.forEach(function (n, j) { pos[n.id] = { x: i * (W + GX), y: off + j * (H + GY) }; });
    });
    edges.forEach(function (e) {
      var a = pos[e[0]], b = pos[e[1]];
      if (!a || !b) return;
      el("path", { d: "M" + (a.x + W) + " " + (a.y + H / 2) + "C" + (a.x + W + GX / 2) + " " + (a.y + H / 2) + " " +
        (b.x - GX / 2) + " " + (b.y + H / 2) + " " + b.x + " " + (b.y + H / 2),
        fill: "none", stroke: "#888", "stroke-width": 1.2, "marker-end": "url(#" + uid + ")" }, svg);
    });
    levels.forEach(function (l) {
      l.forEach(function (n) {
        var p = pos[n.id];
        var a = el("a", { href: href(n, g) }, svg);
        var r = el("rect", { x: p.x, y: p.y, width: W, height: H, rx: 6, fill: n.id === focus ? "#ffe9a8" :
          n.external ? "#eef" : "#f4f4f4", stroke: "#666", "stroke-width": n.id === focus ? 2 : 1 }, a);
        el("title", {}, r).textContent = n.kind + ": " + n.title;
        var t = el("text", { x: p.x + 8, y: p.y + H / 2 + 4, "font-size": 12, fill: "#111" }, a);
        t.textContent = n.kind + ": " + clip(n.title);
      });
    });
    return svg;
  }

  function neighbors(adj, start, depth) {
    var dist = {}, queue = [start];
    dist[start] = 0;
    while (queue.length) {
      var v = queue.shift();
      if (dist[v] >= depth) continue;
      (adj[v] || []).forEach(function (w) { if (!(w in dist)) { dist[w] = dist[v] + 1; queue.push(w); } });
    }
    return dist;
  }

  function perDiv(g, nodes, uses, usedBy) {
    Object.keys(nodes).forEach(function (k) {
      var n = nodes[k];
      if (n.site !== g.site || n.page !== page) return;
      var host = document.getElementById(n.div);
      if (!host || (!(uses[k] || []).length && !(usedBy[k] || []).length)) return;
      var pre = neighbors(uses, k, DEPTH), post = neighbors(usedBy, k, DEPTH);
      var levels = [], d;
      for (d = DEPTH; d >= 1; d--) levels.push(Object.keys(pre).filter(function (x) { return pre[x] === d; }));
      levels.push([k]);
      for (d = 1; d <= DEPTH; d++) levels.push(Object.keys(post).filter(function (x) { return post[x] === d; }));
      levels = levels.filter(function (l) { return l.length; }).map(function (l) { return l.map(function (x) { return nodes[x]; }); });
      var ids = {};
      levels.forEach(function (l) { l.forEach(function (x) { ids[x.id] = 1; }); });
      var edges = g.edges.filter(function (e) { return ids[e[0]] && ids[e[1]]; }).map(function (e) { return [e[1], e[0]]; });
      var det = document.createElement("details");
      det.className = "dependency-graph";
      var sum = document.createElement("summary");
      sum.textContent = "Dependencies (" + (Object.keys(pre).length - 1) + " prerequisites, " +
        (Object.keys(post).length - 1) + " postrequisites, up to " + DEPTH + " levels)";
      det.appendChild(sum);
      var drawn = false;
      det.addEventListener("toggle", function () {
        if (det.open && !drawn) { drawn = true; var s = document.createElement("div"); s.style.overflowX = "auto";
          s.appendChild(draw(levels, edges, k, g)); det.appendChild(s); }
      });
      host.appendChild(det);
    });
  }

  function wholePage(g, nodes, uses) {
    var host = document.getElementById("dependency-graph-page");
    if (!host) return;
    var mine = Object.keys(nodes).filter(function (k) { return nodes[k].site === g.site && nodes[k].page === page; });
    if (!mine.length) return;
    var level = {};
    function lv(k, seen) {
      if (k in level) return level[k];
      if (seen[k]) return 0;
      seen[k] = 1;
      var m = 0;
      (uses[k] || []).forEach(function (p) { if (nodes[p].site === g.site && nodes[p].page === page) m = Math.max(m, lv(p, seen) + 1); });
      return (level[k] = m);
    }
    mine.forEach(function (k) { lv(k, {}); });
    var levels = [];
    mine.forEach(function (k) { (levels[level[k]] = levels[level[k]] || []).push(nodes[k]); });
    var ids = {};
    mine.forEach(function (k) { ids[k] = 1; });
    var edges = g.edges.filter(function (e) { return ids[e[0]] && ids[e[1]]; }).map(function (e) { return [e[1], e[0]]; });
    var s = document.createElement("div");
    s.style.overflow = "auto";
    s.appendChild(draw(levels.filter(Boolean), edges, null, g));
    host.appendChild(s);
  }

  fetch(base + "dependency-graph.json").then(function (r) { return r.json(); }).then(function (g) {
    var nodes = {}, uses = {}, usedBy = {};
    g.nodes.forEach(function (n) { nodes[n.id] = n; });
    g.edges.forEach(function (e) {
      (uses[e[0]] = uses[e[0]] || []).push(e[1]);
      (usedBy[e[1]] = usedBy[e[1]] || []).push(e[0]);
    });
    perDiv(g, nodes, uses, usedBy);
    wholePage(g, nodes, uses);
  }).catch(function () { /* the graph is an extra; a missing file leaves the page as it was */ });
})();
