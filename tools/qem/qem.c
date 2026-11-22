/* Quadrik-Vereinfachung (Garland/Heckbert, Ablauf nach "Fast Quadric Mesh Simplification").
 * Fuer tools/modell_perf.py: verschweisstes Netz rein (nur Positionen), vereinfachtes Netz raus.
 * Merkmalskanten (offene Kanten und Materialgrenzen) werden nur entlang ihrer Linie verkuerzt und
 * mit einer zusaetzlichen Ebene festgehalten: keine Risse, Farbgrenzen bleiben glatt.
 *
 * Aufruf (ctypes): int qem(int nv, double *pos, int nt, int *tri, int *mat, int ziel, double aggr,
 *                          double wrand, double *pos_out, int *tri_out, int *orig_out, int *nv_out)
 * pos_out nv*3, tri_out nt*3, orig_out nt Platz. Rueckgabe: Zahl der Dreiecke; orig_out = Nummer des
 * Eingangsdreiecks (fuer Material und Texturkoordinaten).
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct { double m[10]; } Q;
typedef struct { int v[3]; double err[4]; int del, dirty; double n[3]; int mat, orig; } T;
typedef struct { double p[3]; int tstart, tcount; Q q; int rand, fest; } V;
typedef struct { int tid, tv; } R;

static T *tr; static int ntr;
static V *ve; static int nve;
static R *refs; static int nref, capref;
static double gewicht_rand = 100.0;
static double grenze_entartet = 0.999;
static int flaechengewicht = 0;

static void qplane(Q *q, double a, double b, double c, double d) {
  q->m[0]=a*a; q->m[1]=a*b; q->m[2]=a*c; q->m[3]=a*d; q->m[4]=b*b;
  q->m[5]=b*c; q->m[6]=b*d; q->m[7]=c*c; q->m[8]=c*d; q->m[9]=d*d;
}
static void qadd(Q *a, const Q *b) { for (int i = 0; i < 10; i++) a->m[i] += b->m[i]; }
static double qdet(const Q *q, int a11,int a12,int a13,int a21,int a22,int a23,int a31,int a32,int a33) {
  const double *m = q->m;
  return m[a11]*m[a22]*m[a33] + m[a13]*m[a21]*m[a32] + m[a12]*m[a23]*m[a31]
       - m[a13]*m[a22]*m[a31] - m[a11]*m[a23]*m[a32] - m[a12]*m[a21]*m[a33];
}
static double verr(const Q *q, double x, double y, double z) {
  const double *m = q->m;
  return m[0]*x*x + 2*m[1]*x*y + 2*m[2]*x*z + 2*m[3]*x + m[4]*y*y
       + 2*m[5]*y*z + 2*m[6]*y + m[7]*z*z + 2*m[8]*z + m[9];
}
static void sub(double *r, const double *a, const double *b) { r[0]=a[0]-b[0]; r[1]=a[1]-b[1]; r[2]=a[2]-b[2]; }
static void cross(double *r, const double *a, const double *b) {
  r[0]=a[1]*b[2]-a[2]*b[1]; r[1]=a[2]*b[0]-a[0]*b[2]; r[2]=a[0]*b[1]-a[1]*b[0];
}
static double dot(const double *a, const double *b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
static void norm(double *a) { double l = sqrt(dot(a,a)); if (l > 0) { a[0]/=l; a[1]/=l; a[2]/=l; } }

static double cerr(int i1, int i2, double *p) {
  Q q = ve[i1].q; qadd(&q, &ve[i2].q);
  int rand = ve[i1].rand && ve[i2].rand;
  double det = qdet(&q, 0,1,2,1,4,5,2,5,7);
  if (det != 0 && !rand) {
    p[0] = -1/det*qdet(&q, 1,2,3,4,5,6,5,7,8);
    p[1] =  1/det*qdet(&q, 0,2,3,1,5,6,2,7,8);
    p[2] = -1/det*qdet(&q, 0,1,3,1,4,6,2,5,8);
    /* Schlecht konditioniert (fast parallele Ebenen, duenne Schalen): der "beste" Punkt kann weit weg
       liegen und gibt Stacheln. Dann wie am Rand nur Enden oder Mitte. */
    double *a1 = ve[i1].p, *a2 = ve[i2].p, m[3] = {(a1[0]+a2[0])/2 - p[0], (a1[1]+a2[1])/2 - p[1], (a1[2]+a2[2])/2 - p[2]}, e[3];
    sub(e, a1, a2);
    if (dot(m, m) <= dot(e, e) && isfinite(p[0] + p[1] + p[2])) return verr(&q, p[0], p[1], p[2]);
  }
  double *p1 = ve[i1].p, *p2 = ve[i2].p, p3[3] = {(p1[0]+p2[0])/2, (p1[1]+p2[1])/2, (p1[2]+p2[2])/2};
  double e1 = verr(&q,p1[0],p1[1],p1[2]), e2 = verr(&q,p2[0],p2[1],p2[2]), e3 = verr(&q,p3[0],p3[1],p3[2]);
  double e = fmin(e1, fmin(e2, e3));
  if (e == e1) memcpy(p, p1, 24); else if (e == e2) memcpy(p, p2, 24); else memcpy(p, p3, 24);
  return e;
}

static void pushref(R r) {
  if (nref >= capref) { capref = capref * 2 + 1024; refs = realloc(refs, sizeof(R) * capref); }
  refs[nref++] = r;
}

static int flipped(const double *p, int i1, V *v0, char *del) {
  for (int k = 0; k < v0->tcount; k++) {
    T *t = &tr[refs[v0->tstart + k].tid];
    if (t->del) continue;
    int s = refs[v0->tstart + k].tv, id1 = t->v[(s+1)%3], id2 = t->v[(s+2)%3];
    if (id1 == i1 || id2 == i1) { del[k] = 1; continue; }
    double d1[3], d2[3], n[3];
    sub(d1, ve[id1].p, p); norm(d1); sub(d2, ve[id2].p, p); norm(d2);
    if (fabs(dot(d1, d2)) > grenze_entartet) return 1;
    cross(n, d1, d2); norm(n);
    del[k] = 0;
    if (dot(n, t->n) < 0.2) return 1;
  }
  return 0;
}

static int merkmal(int a, int b) {
  int n = 0, m0 = -1, versch = 0;
  for (int k = 0; k < ve[a].tcount; k++) {
    T *t = &tr[refs[ve[a].tstart + k].tid];
    if (t->del) continue;
    if (t->v[0] == b || t->v[1] == b || t->v[2] == b) { if (n == 0) m0 = t->mat; else if (t->mat != m0) versch = 1; n++; }
  }
  return n == 1 || versch;
}

static void upd_tris(int i0, V *v, char *del, int *dc) {
  double p[3];
  for (int k = 0; k < v->tcount; k++) {
    R r = refs[v->tstart + k];
    T *t = &tr[r.tid];
    if (t->del) continue;
    if (del[k]) { t->del = 1; (*dc)++; continue; }
    t->v[r.tv] = i0; t->dirty = 1;
    t->err[0] = cerr(t->v[0], t->v[1], p); t->err[1] = cerr(t->v[1], t->v[2], p);
    t->err[2] = cerr(t->v[2], t->v[0], p);
    t->err[3] = fmin(t->err[0], fmin(t->err[1], t->err[2]));
    pushref(r);
  }
}

static void upd_mesh(int it) {
  if (it > 0) { int d = 0; for (int i = 0; i < ntr; i++) if (!tr[i].del) tr[d++] = tr[i]; ntr = d; }
  for (int i = 0; i < nve; i++) { ve[i].tstart = 0; ve[i].tcount = 0; }
  for (int i = 0; i < ntr; i++) for (int j = 0; j < 3; j++) ve[tr[i].v[j]].tcount++;
  int ts = 0;
  for (int i = 0; i < nve; i++) { ve[i].tstart = ts; ts += ve[i].tcount; ve[i].tcount = 0; }
  nref = ts; if (capref < ts) { capref = ts; refs = realloc(refs, sizeof(R) * capref); }
  for (int i = 0; i < ntr; i++) for (int j = 0; j < 3; j++) {
    V *v = &ve[tr[i].v[j]]; refs[v->tstart + v->tcount].tid = i; refs[v->tstart + v->tcount].tv = j; v->tcount++;
  }
  if (it == 0) {
    /* Merkmalskanten: offene Kante (nur EIN Dreieck) oder Materialgrenze (Dreiecke verschiedenen
       Materials). Ecken daran heissen "rand"; Ecken mit mehr oder weniger als zwei Merkmalskanten
       (Ecken der Grenzlinie, Enden) sind fest. */
    int *vc = NULL, *vi = NULL, *vm = NULL, *vd = NULL, cap = 0;
    for (int i = 0; i < nve; i++) { ve[i].rand = 0; ve[i].fest = 0; }
    int *nmk = calloc(nve, sizeof(int));
    for (int i = 0; i < nve; i++) {
      int n = 0;
      if (cap < ve[i].tcount * 3) { cap = ve[i].tcount * 3 + 16; vc = realloc(vc, 4*cap); vi = realloc(vi, 4*cap); vm = realloc(vm, 4*cap); vd = realloc(vd, 4*cap); }
      for (int k = 0; k < ve[i].tcount; k++) {
        T *t = &tr[refs[ve[i].tstart + k].tid];
        for (int j = 0; j < 3; j++) {
          int id = t->v[j], f = 0;
          if (id == i) continue;
          for (; f < n; f++) if (vi[f] == id) { vc[f]++; if (vm[f] != t->mat) vd[f] = 1; break; }
          if (f == n) { vi[n] = id; vc[n] = 1; vm[n] = t->mat; vd[n] = 0; n++; }
        }
      }
      for (int f = 0; f < n; f++) if (vc[f] == 1 || vd[f]) { ve[i].rand = 1; nmk[i]++; }
    }
    for (int i = 0; i < nve; i++) if (ve[i].rand && (nmk[i] == 1 || nmk[i] == 3 || nmk[i] > 4)) ve[i].fest = 1;
    free(nmk); free(vc); free(vi); free(vm); free(vd);
    for (int i = 0; i < nve; i++) memset(&ve[i].q, 0, sizeof(Q));
    for (int i = 0; i < ntr; i++) {
      T *t = &tr[i]; double a[3], b[3], n[3];
      sub(a, ve[t->v[1]].p, ve[t->v[0]].p); sub(b, ve[t->v[2]].p, ve[t->v[0]].p);
      cross(n, a, b); double fl = sqrt(dot(n, n)) * 0.5; norm(n); memcpy(t->n, n, 24);
      Q q; qplane(&q, n[0], n[1], n[2], -dot(n, ve[t->v[0]].p));
      /* Flaechengewicht (QEM_FLAECHE=1): grosse glatte Flaechen zaehlen mehr als dichte Kleinteile */
      if (flaechengewicht) for (int k = 0; k < 10; k++) q.m[k] *= fl;
      for (int j = 0; j < 3; j++) qadd(&ve[t->v[j]].q, &q);
    }
    /* Randquadrik: Ebene durch die Merkmalskante, senkrecht zur Flaeche - haelt die Linie an ihrem Ort */
    for (int i = 0; i < ntr; i++) {
      T *t = &tr[i];
      for (int j = 0; j < 3; j++) {
        int a = t->v[j], b = t->v[(j+1)%3];
        if (!ve[a].rand || !ve[b].rand || !merkmal(a, b)) continue;
        double e[3], nb[3]; sub(e, ve[b].p, ve[a].p);
        double l2 = dot(e, e);
        cross(nb, e, t->n); norm(nb);
        Q q; qplane(&q, nb[0], nb[1], nb[2], -dot(nb, ve[a].p));
        for (int k = 0; k < 10; k++) q.m[k] *= gewicht_rand * (l2 > 0 ? 1 : 0);
        qadd(&ve[a].q, &q); qadd(&ve[b].q, &q);
      }
    }
    double p[3];
    for (int i = 0; i < ntr; i++) {
      T *t = &tr[i];
      for (int j = 0; j < 3; j++) t->err[j] = cerr(t->v[j], t->v[(j+1)%3], p);
      t->err[3] = fmin(t->err[0], fmin(t->err[1], t->err[2]));
    }
  }
}

int qem(int nv, double *pos, int nt, int *tri, int *mat, int ziel, double aggr, double wrand, double *pos_out, int *tri_out, int *orig_out, int *nv_out) {
  gewicht_rand = wrand;
  { const char *g = getenv("QEM_ENTARTET"); if (g) grenze_entartet = atof(g); }
  { const char *g = getenv("QEM_FLAECHE"); flaechengewicht = g && atoi(g); }
  nve = nv; ntr = nt;
  ve = calloc(nv, sizeof(V)); tr = calloc(nt, sizeof(T)); refs = NULL; nref = capref = 0;
  for (int i = 0; i < nv; i++) memcpy(ve[i].p, pos + 3*i, 24);
  for (int i = 0; i < nt; i++) { memcpy(tr[i].v, tri + 3*i, 12); tr[i].mat = mat[i]; tr[i].orig = i; }
  int dc = 0, alt = ntr;
  char *d0 = malloc(1), *d1 = malloc(1); int dcap = 1;
  for (int it = 0; it < 200; it++) {
    if (alt - dc <= ziel) break;
    if (it % 5 == 0) upd_mesh(it);
    for (int i = 0; i < ntr; i++) tr[i].dirty = 0;
    double schwelle = 0.000000001 * pow(it + 3, aggr);
    for (int i = 0; i < ntr; i++) {
      T *t = &tr[i];
      if (t->err[3] > schwelle || t->del || t->dirty) continue;
      for (int j = 0; j < 3; j++) if (t->err[j] < schwelle) {
        int i0 = t->v[j], i1 = t->v[(j+1)%3];
        V *v0 = &ve[i0], *v1 = &ve[i1];
        if (v0->fest || v1->fest) continue;
        if (v0->rand != v1->rand) continue;
        if (v0->rand && !merkmal(i0, i1)) continue;     /* Randecken nur entlang ihrer Linie */
        double p[3]; cerr(i0, i1, p);
        int need = v0->tcount > v1->tcount ? v0->tcount : v1->tcount;
        if (need > dcap) { dcap = need * 2; d0 = realloc(d0, dcap); d1 = realloc(d1, dcap); }
        if (flipped(p, i1, v0, d0)) continue;
        if (flipped(p, i0, v1, d1)) continue;
        memcpy(v0->p, p, 24); qadd(&v0->q, &v1->q);
        int ts = nref;
        upd_tris(i0, v0, d0, &dc);
        upd_tris(i0, v1, d1, &dc);
        int tc = nref - ts;
        if (tc <= v0->tcount) { if (tc) memmove(&refs[v0->tstart], &refs[ts], tc * sizeof(R)); }
        else v0->tstart = ts;
        v0->tcount = tc;
        break;
      }
      if (alt - dc <= ziel) break;
    }
  }
  /* zusammenschieben */
  int nt2 = 0;
  int *map = malloc(sizeof(int) * nve); for (int i = 0; i < nve; i++) map[i] = -1;
  int nv2 = 0;
  for (int i = 0; i < ntr; i++) if (!tr[i].del) {
    for (int j = 0; j < 3; j++) {
      int v = tr[i].v[j];
      if (map[v] < 0) { map[v] = nv2; memcpy(pos_out + 3*nv2, ve[v].p, 24); nv2++; }
      tri_out[3*nt2 + j] = map[v];
    }
    orig_out[nt2] = tr[i].orig;
    nt2++;
  }
  *nv_out = nv2;
  free(map); free(ve); free(tr); free(refs); free(d0); free(d1); refs = NULL;
  return nt2;
}
