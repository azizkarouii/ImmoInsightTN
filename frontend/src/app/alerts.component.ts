import { API_BASE } from './api.config';
import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

type Onglet = 'nouvelles' | 'prix' | 'opportunites' | 'supprimees' | 'fiabilite';
type Collection = 'clean_vente' | 'clean_location' | 'clean_estival';

interface Job {
  id: string;
  label: string;
  description: string;
  frequence: string;
  prochaine_execution: string | null;
  derniere_execution: { debut: string; fin?: string; statut: string; duree_s?: number; resume?: string[] } | null;
}

@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="card">
      <div class="section-head">
        <div>
          <p class="eyebrow">Veille active</p>
          <h2>Alertes marché</h2>
          <p class="section-copy">
            Nouvelles annonces, variations de prix, biens affichés sous l'estimation des modèles et annonces retirées,
            alimentés par la collecte automatique.
          </p>
        </div>
        <div class="filter-bar">
          <div class="segmented">
            <button *ngFor="let c of collections" [class.active]="collection === c.id"
                    [disabled]="onglet === 'fiabilite' && c.id !== 'clean_vente'"
                    (click)="setCollection(c.id)">{{ c.label }}</button>
          </div>
          <div class="segmented">
            <button *ngFor="let j of periodes" [class.active]="jours === j" (click)="setJours(j)">{{ j === 1 ? '24 h' : j + ' j' }}</button>
          </div>
        </div>
      </div>

      <div class="kpi-grid">
        <button *ngFor="let k of kpis" class="kpi-card" [class.active]="onglet === k.id"
                [class.disabled]="k.id === 'opportunites' && collection === 'clean_estival'"
                (click)="setOnglet(k.id)">
          <span class="kpi-icon">{{ k.icon }}</span>
          <strong>{{ compteur(k.id) ?? '—' }}</strong>
          <span>{{ k.label }}</span>
          <small>{{ k.id === 'prix' && resume ? detailVariations() : k.aide }}</small>
        </button>
      </div>

      <!-- Spinner plein écran seulement au premier chargement d'un onglet : pendant une
           recherche ou un tri, la barre de recherche et le tableau restent affichés (le
           champ de saisie n'est pas recréé et garde le focus) -->
      <div *ngIf="loading && !rows.length" class="loading"><div class="spinner"></div>Chargement...</div>
      <div *ngIf="error" class="result-box" style="background:#fbe9e7"><p style="color:#c62828">⚠️ {{ error }}</p></div>
      <div *ngIf="avertissement" class="notice">{{ avertissement }}</div>

      <ng-container *ngIf="rows.length || !loading">
        <div class="table-toolbar" *ngIf="onglet === 'nouvelles'">
          <div class="search-box">
            <span aria-hidden="true">🔍</span>
            <input type="search" [ngModel]="recherche" (ngModelChange)="rechercher($event)" maxlength="100"
                   placeholder="Rechercher par titre, ville, quartier… (ex. « villa la marsa »)" aria-label="Rechercher dans les nouvelles annonces" />
            <button *ngIf="recherche" type="button" (click)="rechercher('')" aria-label="Effacer la recherche">✕</button>
          </div>
        </div>

        <p class="table-caption" *ngIf="rows.length && !error">
          {{ titreTableau() }} — {{ total | number }} {{ recherche && onglet === 'nouvelles' ? 'résultat(s) pour « ' + recherche + ' »' : 'au total' }},
          triées par {{ libelleTri() }}<span class="maj" *ngIf="loading"> · mise à jour…</span>
        </p>

        <div class="table-wrap" *ngIf="rows.length && !error" [class.en-maj]="loading">
          <table>
            <thead>
              <tr>
                <th>Annonce</th>
                <th *ngFor="let c of colonnes[onglet]" class="th-tri" [class.actif]="tri.cle === c.cle"
                    [attr.aria-sort]="tri.cle === c.cle ? (tri.ordre === 'asc' ? 'ascending' : 'descending') : 'none'">
                  <button type="button" (click)="trier(c.cle)" [title]="'Trier par ' + c.libelle.toLowerCase()">
                    {{ c.libelle }}
                    <span class="tri-icone" aria-hidden="true">{{ tri.cle === c.cle ? (tri.ordre === 'asc' ? '▲' : '▼') : '↕' }}</span>
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr *ngFor="let r of lignes.slice(0, affichees)">
                <td class="cell-title">
                  <a *ngIf="r.url; else sansLien" [href]="r.url" target="_blank" rel="noopener">{{ r.titre || 'Sans titre' }}</a>
                  <ng-template #sansLien>{{ r.titre || 'Sans titre' }}</ng-template>
                  <span class="badge badge-info source-badge">{{ r.source }}</span>
                </td>
                <td class="muted">{{ lieu(r) }}</td>
                <ng-container [ngSwitch]="onglet">
                  <ng-container *ngSwitchCase="'prix'">
                    <td>{{ r.ancien_prix | number:'1.0-0' }} {{ unite() }}</td>
                    <td><strong>{{ r.nouveau_prix | number:'1.0-0' }} {{ unite() }}</strong></td>
                    <td><span class="badge" [class.badge-success]="r.variation_pct < 0" [class.badge-danger]="r.variation_pct > 0">
                      {{ r.variation_pct > 0 ? '+' : '' }}{{ r.variation_pct }} %</span></td>
                    <td class="muted">{{ dateCourte(r.date_changement) }}</td>
                  </ng-container>
                  <ng-container *ngSwitchCase="'opportunites'">
                    <td><strong>{{ r.prix | number:'1.0-0' }} {{ unite() }}</strong></td>
                    <td class="muted">{{ r.prix_estime | number:'1.0-0' }} {{ unite() }}</td>
                    <td><span class="badge badge-success">{{ r.ecart_estimation_pct }} %</span></td>
                  </ng-container>
                  <ng-container *ngSwitchCase="'supprimees'">
                    <td>{{ r.prix | number:'1.0-0' }} {{ unite() }}</td>
                    <td class="muted">{{ dateCourte(r.supprime_le) }}</td>
                  </ng-container>
                  <ng-container *ngSwitchCase="'fiabilite'">
                    <td>{{ r.prix | number:'1.0-0' }} TND</td>
                    <td><span class="badge" [class.badge-danger]="r.fiabilite <= 15" [class.badge-warning]="r.fiabilite > 15">{{ r.fiabilite }}/100</span></td>
                  </ng-container>
                  <ng-container *ngSwitchDefault>
                    <td class="muted">{{ r.surface ? (r.surface + ' m²') : '—' }}</td>
                    <td><strong>{{ r.prix | number:'1.0-0' }} {{ unite() }}</strong></td>
                    <td>
                      <span *ngIf="r.ecart_estimation_pct !== null && r.ecart_estimation_pct !== undefined; else tiret" class="badge"
                            [class.badge-success]="r.ecart_estimation_pct < -10" [class.badge-warning]="r.ecart_estimation_pct > 10"
                            [class.badge-info]="r.ecart_estimation_pct >= -10 && r.ecart_estimation_pct <= 10">
                        {{ r.ecart_estimation_pct > 0 ? '+' : '' }}{{ r.ecart_estimation_pct }} %</span>
                      <ng-template #tiret><span class="muted">—</span></ng-template>
                    </td>
                    <td class="muted">{{ depuis(r.first_seen) }}</td>
                  </ng-container>
                </ng-container>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="table-more" *ngIf="rows.length > affichees">
          <button class="btn" (click)="affichees = affichees + pas">Afficher {{ pas }} de plus ({{ rows.length - affichees }} restantes)</button>
        </div>

        <div *ngIf="!rows.length && !loading && !error" class="empty-state">
          <ng-container *ngIf="recherche && onglet === 'nouvelles'; else videPeriode">
            <strong>Aucune annonce ne correspond à « {{ recherche }} ».</strong>
            <span>Essayez un autre mot (ville, quartier, type de bien) ou élargissez la période.</span>
          </ng-container>
          <ng-template #videPeriode>
            <strong>Aucune alerte « {{ titreTableau().toLowerCase() }} » sur la période.</strong>
            <span>{{ aideVide() }}</span>
          </ng-template>
        </div>
      </ng-container>
    </div>

    <div class="card" style="margin-top:20px">
      <div class="section-head">
        <div>
          <p class="eyebrow">Automatisation</p>
          <h2>Collecte automatique</h2>
          <p class="section-copy">
            Planning du scheduler (fuseau Africa/Tunis) et résultat des dernières exécutions.
            Démarrage : <code>python -m scrapers.main --scheduler</code>
          </p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ derniereCollecte() }}</strong> dernière collecte</div>
        </div>
      </div>

      <div *ngIf="schedulerInactif()" class="notice">
        Aucune exécution planifiée depuis plus de 26 h : le scheduler ne semble pas démarré.
      </div>

      <div class="table-wrap">
        <table>
          <thead><tr><th>Tâche</th><th>Fréquence</th><th>Prochaine exécution</th><th>Dernière exécution</th></tr></thead>
          <tbody>
            <tr *ngFor="let job of jobs">
              <td class="cell-title">
                <strong>{{ job.label }}</strong>
                <div class="muted small">{{ job.description }}</div>
              </td>
              <td class="muted">{{ job.frequence }}</td>
              <td>{{ dateCourte(job.prochaine_execution) }}<div class="muted small">{{ dans(job.prochaine_execution) }}</div></td>
              <td>
                <ng-container *ngIf="job.derniere_execution as d; else jamais">
                  <span class="badge" [class.badge-success]="d.statut === 'succes'" [class.badge-danger]="d.statut === 'echec' || d.statut === 'timeout'"
                        [class.badge-info]="d.statut === 'en_cours'">{{ libelleStatut(d.statut) }}</span>
                  <div class="muted small">{{ dateCourte(d.debut, true) }}{{ d.duree_s ? ' · ' + duree(d.duree_s) : '' }}</div>
                </ng-container>
                <ng-template #jamais><span class="muted">Jamais exécutée</span></ng-template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: []
})
export class AlertsComponent implements OnInit {
  collections: { id: Collection; label: string }[] = [
    { id: 'clean_vente', label: 'Vente' },
    { id: 'clean_location', label: 'Location' },
    { id: 'clean_estival', label: 'Estival' },
  ];
  periodes = [1, 7, 30];
  kpis: { id: Onglet; icon: string; label: string; aide: string }[] = [
    { id: 'nouvelles', icon: '🆕', label: 'Nouvelles annonces', aide: 'apparues sur la période' },
    { id: 'prix', icon: '📉', label: 'Variations de prix', aide: 'baisses et hausses sur la période' },
    { id: 'opportunites', icon: '💎', label: 'Opportunités', aide: 'prix nettement sous l\'estimation' },
    { id: 'supprimees', icon: '🚫', label: 'Annonces retirées', aide: 'vérifiées hors ligne' },
    { id: 'fiabilite', icon: '⚠️', label: 'Fiabilité faible', aide: 'score M4 ≤ 30 (vente)' },
  ];

  onglet: Onglet = 'nouvelles';
  collection: Collection = 'clean_vente';
  jours = 7;
  loading = false;
  error: string | null = null;
  avertissement: string | null = null;
  rows: any[] = [];
  lignes: any[] = [];   // rows triées (calculées une fois, pas dans un getter)
  total = 0;
  recherche = '';
  private recherche$ = new Subject<string>();

  // Colonnes triables par onglet. Nouvelles annonces : tri côté serveur (sur toute la
  // base, pas seulement les lignes chargées) ; autres onglets : tri des lignes affichées.
  colonnes: Record<Onglet, { cle: string; libelle: string }[]> = {
    nouvelles: [
      { cle: 'lieu', libelle: 'Lieu' }, { cle: 'surface', libelle: 'Surface' }, { cle: 'prix', libelle: 'Prix' },
      { cle: 'estimation', libelle: 'Vs estimation' }, { cle: 'publiee', libelle: 'Publiée' },
    ],
    prix: [
      { cle: 'lieu', libelle: 'Lieu' }, { cle: 'ancien_prix', libelle: 'Ancien prix' }, { cle: 'nouveau_prix', libelle: 'Nouveau prix' },
      { cle: 'variation_pct', libelle: 'Variation' }, { cle: 'date_changement', libelle: 'Changé le' },
    ],
    opportunites: [
      { cle: 'lieu', libelle: 'Lieu' }, { cle: 'prix', libelle: 'Prix affiché' }, { cle: 'prix_estime', libelle: 'Estimation' },
      { cle: 'ecart_estimation_pct', libelle: 'Écart' },
    ],
    supprimees: [{ cle: 'lieu', libelle: 'Lieu' }, { cle: 'prix', libelle: 'Dernier prix' }, { cle: 'supprime_le', libelle: 'Retirée le' }],
    fiabilite: [{ cle: 'lieu', libelle: 'Lieu' }, { cle: 'prix', libelle: 'Prix' }, { cle: 'fiabilite', libelle: 'Fiabilité' }],
  };
  private trisParDefaut: Record<Onglet, { cle: string; ordre: 'asc' | 'desc' }> = {
    nouvelles: { cle: 'publiee', ordre: 'desc' },
    prix: { cle: 'variation_pct', ordre: 'asc' },
    opportunites: { cle: 'ecart_estimation_pct', ordre: 'asc' },
    supprimees: { cle: 'supprime_le', ordre: 'desc' },
    fiabilite: { cle: 'fiabilite', ordre: 'asc' },
  };
  tri = { ...this.trisParDefaut.nouvelles };
  pas = 20;
  affichees = 20;
  resume: any = null;
  jobs: Job[] = [];
  private request: Subscription | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    // Recherche déclenchée 300 ms après la dernière frappe
    this.recherche$.pipe(debounceTime(300), distinctUntilChanged()).subscribe(() => this.chargerTableau(true));
    this.charger();
    this.http.get<{ jobs: Job[] }>(API_BASE + '/api/alertes/scheduler')
      .subscribe({ next: res => this.jobs = res.jobs || [], error: () => this.jobs = [] });
  }

  setOnglet(onglet: Onglet): void {
    if (onglet === 'opportunites' && this.collection === 'clean_estival') return;
    this.onglet = onglet;
    this.tri = { ...this.trisParDefaut[onglet] };
    if (onglet === 'fiabilite') this.collection = 'clean_vente';
    this.chargerTableau();
  }

  /** 1er clic : croissant ; clic suivant sur la même colonne : décroissant (et inversement). */
  trier(cle: string): void {
    this.tri = this.tri.cle === cle
      ? { cle, ordre: this.tri.ordre === 'asc' ? 'desc' : 'asc' }
      : { cle, ordre: 'asc' };
    if (this.onglet === 'nouvelles') {
      this.chargerTableau(true);      // tri sur toute la base, côté serveur
    } else {
      this.affichees = this.pas;
      this.lignes = this.trierLocalement(this.rows);
    }
  }

  rechercher(texte: string): void {
    this.recherche = texte;
    this.recherche$.next(texte.trim());
  }

  libelleTri(): string {
    const col = this.colonnes[this.onglet].find(c => c.cle === this.tri.cle);
    const nom = ({ publiee: 'date de publication', estimation: 'écart à l\'estimation', supprime_le: 'date de retrait',
                   date_changement: 'date de changement' } as Record<string, string>)[this.tri.cle] ?? (col?.libelle ?? '').toLowerCase();
    return `${nom} (${this.tri.ordre === 'asc' ? 'croissant' : 'décroissant'})`;
  }

  private valeurTri(r: any, cle: string): string | number | null {
    if (cle === 'lieu') return this.lieu(r) === '—' ? null : this.lieu(r);
    const v = r?.[cle];
    return v === undefined || v === '' ? null : v;
  }

  private trierLocalement(rows: any[]): any[] {
    const { cle, ordre } = this.tri;
    const sens = ordre === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = this.valeurTri(a, cle), vb = this.valeurTri(b, cle);
      // Valeurs manquantes toujours en fin de liste
      if (va === null || vb === null) return va === null ? (vb === null ? 0 : 1) : -1;
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sens;
      return String(va).localeCompare(String(vb), 'fr', { sensitivity: 'base', numeric: true }) * sens;
    });
  }

  setCollection(collection: Collection): void {
    this.collection = collection;
    if (collection === 'clean_estival' && this.onglet === 'opportunites') this.onglet = 'nouvelles';
    this.chargerTableau();
  }

  setJours(jours: number): void {
    this.jours = jours;
    this.charger();
  }

  compteur(onglet: Onglet): number | null {
    const c = this.resume?.collections?.[this.collection];
    if (!this.resume) return null;
    switch (onglet) {
      case 'nouvelles': return c?.nouvelles ?? 0;
      case 'prix': return (c?.baisses_prix ?? 0) + (c?.hausses_prix ?? 0);
      case 'opportunites': return c?.opportunites ?? 0;
      case 'supprimees': return c?.retirees ?? 0;
      case 'fiabilite': return this.resume.fiabilite_faible ?? 0;
    }
  }

  private charger(): void {
    this.http.get<any>(API_BASE + '/api/alertes/resume', { params: { jours: this.jours } })
      .subscribe({ next: res => this.resume = res, error: () => this.resume = null });
    this.chargerTableau();
  }

  /** conserver : garder les lignes affichées pendant le chargement (recherche, tri)
   *  au lieu de vider l'écran (changement d'onglet, de collection ou de période). */
  private chargerTableau(conserver = false): void {
    this.request?.unsubscribe();
    this.affichees = this.pas;
    this.loading = true;
    this.error = null;
    if (!conserver) {
      this.rows = [];
      this.lignes = [];
    }
    const urls: Record<Onglet, string> = {
      nouvelles: '/api/alertes/nouvelles',
      prix: '/api/alertes/prix',
      opportunites: '/api/alertes/opportunites',
      supprimees: '/api/alertes/supprimees',
      fiabilite: '/api/fiabilite/alertes',
    };
    const params: Record<string, string | number> = { limit: 100 };
    if (this.onglet !== 'fiabilite') params['collection'] = this.collection;
    if (['nouvelles', 'prix', 'supprimees'].includes(this.onglet)) params['jours'] = this.jours;
    if (this.onglet === 'nouvelles') {
      params['tri'] = this.tri.cle;
      params['ordre'] = this.tri.ordre;
      if (this.recherche.trim()) params['q'] = this.recherche.trim();
    }

    this.request = this.http.get<any>(API_BASE + urls[this.onglet], { params }).subscribe({
      next: res => {
        this.rows = Array.isArray(res?.data) ? res.data : [];
        this.lignes = this.onglet === 'nouvelles' ? this.rows : this.trierLocalement(this.rows);
        this.total = Number(res?.count ?? res?.total ?? this.rows.length);
        // Une API lancée avant l'ajout de la recherche ignore q/tri sans erreur
        this.avertissement = this.onglet === 'nouvelles' && res && res.tri === undefined
          ? "L'API ne gère pas encore la recherche et le tri : redémarrez le serveur FastAPI (port 8000)."
          : null;
        this.loading = false;
      },
      error: err => {
        this.rows = [];
        this.lignes = [];
        this.loading = false;
        this.error = err?.status ? `Erreur serveur (${err.status})` : 'Erreur de connexion au serveur';
      },
    });
  }

  detailVariations(): string {
    const c = this.resume?.collections?.[this.collection];
    return `${c?.baisses_prix ?? 0} baisse(s) · ${c?.hausses_prix ?? 0} hausse(s)`;
  }

  titreTableau(): string {
    return this.kpis.find(k => k.id === this.onglet)?.label ?? '';
  }

  aideVide(): string {
    switch (this.onglet) {
      case 'prix': return 'Les variations apparaissent quand une annonce déjà connue est revue avec un autre prix (passage complet hebdomadaire).';
      case 'supprimees': return 'La vérification quotidienne re-visite les annonces non revues depuis 14 jours.';
      case 'opportunites': return 'Calculées après chaque ETL à partir des estimations hors échantillon des modèles.';
      default: return 'Élargissez la période ou changez de collection.';
    }
  }

  unite(): string {
    if (this.collection === 'clean_estival') return 'TND/nuit';
    if (this.collection === 'clean_location') return 'TND/mois';
    return 'TND';
  }

  lieu(r: any): string {
    return [r.ville, r.gouvernorat].filter((v, i, a) => v && a.indexOf(v) === i).join(', ') || '—';
  }

  dateCourte(val: string | null | undefined, heure = true): string {
    if (!val) return '—';
    // Les dates du backend sont en UTC sans fuseau explicite
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(val) ? val : val + 'Z');
    if (Number.isNaN(d.getTime())) return String(val).slice(0, 16);
    return new Intl.DateTimeFormat('fr-FR', heure ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(d);
  }

  private ecartHeures(val: string | null | undefined): number | null {
    if (!val) return null;
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(val) ? val : val + 'Z');
    return Number.isNaN(d.getTime()) ? null : (d.getTime() - Date.now()) / 3_600_000;
  }

  depuis(val: string | null | undefined): string {
    const h = this.ecartHeures(val);
    if (h === null) return '—';
    const passe = -h;
    if (passe < 1) return "à l'instant";
    if (passe < 24) return `il y a ${Math.round(passe)} h`;
    return `il y a ${Math.round(passe / 24)} j`;
  }

  dans(val: string | null | undefined): string {
    const h = this.ecartHeures(val);
    if (h === null) return '';
    if (h < 1) return `dans ${Math.max(1, Math.round(h * 60))} min`;
    if (h < 48) return `dans ${Math.round(h)} h`;
    return `dans ${Math.round(h / 24)} j`;
  }

  duree(s: number): string {
    return s < 60 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`;
  }

  libelleStatut(statut: string): string {
    return ({ succes: 'Succès', echec: 'Échec', timeout: 'Délai dépassé', en_cours: 'En cours' } as Record<string, string>)[statut] ?? statut;
  }

  derniereCollecte(): string {
    const debuts = this.jobs.map(j => j.derniere_execution?.debut).filter((d): d is string => !!d).sort();
    return debuts.length ? this.depuis(debuts[debuts.length - 1]) : 'aucune';
  }

  schedulerInactif(): boolean {
    const debuts = this.jobs.map(j => j.derniere_execution?.debut).filter((d): d is string => !!d).sort();
    if (!this.jobs.length) return false;
    if (!debuts.length) return true;
    const h = this.ecartHeures(debuts[debuts.length - 1]);
    return h !== null && -h > 26;
  }
}
