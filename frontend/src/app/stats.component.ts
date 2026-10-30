import { API_BASE } from './api.config';
import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, QueryList, ViewChildren } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { CommonModule } from '@angular/common';
import Chart, { ChartConfiguration } from 'chart.js/auto';

// Couleurs par entité, identiques sur toute la page (palette validée daltonisme)
const SEGMENT = { vente: '#2a78d6', location: '#eb6834', estival: '#1baf7a' } as const;
const TYPE_BIEN: Record<string, string> = { appartement: '#6250d6', villa: '#eda100', maison_vacances: '#e87ba4' };
const NEUTRE = '#13204a';
const ENCRE = '#526173';
const GRILLE = 'rgba(18, 32, 54, 0.07)';
const LIBELLE_TYPE: Record<string, string> = { appartement: 'Appartement', villa: 'Villa / maison', maison_vacances: 'Maison de vacances' };
const LIBELLE_SEGMENT: Record<string, string> = { vente: 'Vente', location: 'Location', estival: 'Estival' };
// Sources : rouge et vert jamais adjacents dans la barre empilée (séparés par le bleu), pourcentages écrits sur les barres
const SOURCE: Record<string, string> = { tayara: '#e34948', mubawab: '#184f95', booking: '#008300' };
const AUTRE_SOURCE = '#8a94a6';

/** Écrit la valeur au centre de chaque segment assez large (barres empilées horizontales). */
const etiquettesSegments = {
  id: 'etiquettesSegments',
  afterDatasetsDraw(chart: any) {
    const ctx = chart.ctx;
    ctx.save();
    ctx.font = '600 11px Inter, system-ui, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    chart.data.datasets.forEach((ds: any, i: number) => {
      if (!chart.isDatasetVisible(i)) return;
      chart.getDatasetMeta(i).data.forEach((barre: any, j: number) => {
        const v = Number(ds.data[j]);
        if (v && Math.abs(barre.x - barre.base) >= 28) ctx.fillText(`${Math.round(v)} %`, (barre.x + barre.base) / 2, barre.y);
      });
    });
    ctx.restore();
  },
};

interface Graphique {
  id: string;
  section: string;
  titre: string;
  aide?: string;
  large?: boolean;
  config: ChartConfiguration | null;
  tableau: { colonnes: string[]; lignes: (string | number)[][] } | null;
  voirTableau: boolean;
  vide?: string;
}

const nf = (v: number, d = 0) => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: d });

@Component({
  selector: 'app-stats',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" style="margin-bottom:20px">
      <div class="section-head">
        <div>
          <p class="eyebrow">Lecture du marché</p>
          <h2>Volumes, prix et rentabilité</h2>
          <p class="section-copy">
            Médianes calculées sur les annonces nettoyées (moins sensibles aux biens de luxe que les moyennes).
          </p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ stats?.global_geo_coverage_pct ?? '—' }}%</strong> couverture GPS</div>
          <div class="summary-pill"><strong>{{ marche?.kpis?.nb_villes ?? '—' }}</strong> villes et quartiers</div>
        </div>
      </div>

      <div class="summary-grid kpi-8">
        <div class="summary-tile" *ngFor="let k of kpis">
          <span>{{ k.libelle }}</span>
          <strong>{{ k.valeur }}</strong>
          <small *ngIf="k.aide">{{ k.aide }}</small>
        </div>
      </div>

      <div class="stats-grid">
        <div class="card stat-card" [class.vente]="item.name !== 'estival'" [class.estival]="item.name === 'estival'" *ngFor="let item of collections">
          <div class="stat-value">{{ item.total | number }}</div>
          <div class="stat-label">{{ labelForCollection(item.name) }}</div>
          <div class="stat-sub">
            {{ item.nouveaux_7j | number }} nouvelles (7 j) · {{ item.couverture_gps_pct }}% GPS · qualité {{ item.qualite_moyenne ?? '—' }}/100
          </div>
        </div>
      </div>
    </div>

    <nav class="stats-nav" aria-label="Aller à une section">
      <button type="button" *ngFor="let s of sections" (click)="allerA(s.id)">{{ s.titre }}</button>
      <button type="button" (click)="allerA('qualite')">Qualité des données</button>
    </nav>

    <section class="stats-section" *ngFor="let s of sections" [id]="'stats-' + s.id">
      <div class="stats-section-head">
        <h3>{{ s.titre }}</h3>
        <p>{{ s.description }}</p>
      </div>
      <div class="charts-grid">
        <div class="card chart-card" *ngFor="let g of parSection(s.id)" [class.chart-large]="g.large">
          <div class="chart-card-head">
            <div>
              <h3>{{ g.titre }}</h3>
              <p class="chart-aide" *ngIf="g.aide">{{ g.aide }}</p>
            </div>
            <button class="chart-toggle" *ngIf="g.tableau" (click)="g.voirTableau = !g.voirTableau"
                    [attr.aria-pressed]="g.voirTableau">{{ g.voirTableau ? 'Graphique' : 'Données' }}</button>
          </div>
          <div class="chart-box" [hidden]="g.voirTableau || !g.config"><canvas #canvas [attr.data-id]="g.id"></canvas></div>
          <div class="chart-vide" *ngIf="!g.config && !g.voirTableau">{{ g.vide || 'Chargement…' }}</div>
          <div class="chart-table" *ngIf="g.voirTableau && g.tableau">
            <table>
              <thead><tr><th *ngFor="let c of g.tableau.colonnes">{{ c }}</th></tr></thead>
              <tbody><tr *ngFor="let l of g.tableau.lignes"><td *ngFor="let v of l">{{ v }}</td></tr></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section class="stats-section" id="stats-qualite">
      <div class="stats-section-head">
        <h3>Qualité des données</h3>
        <p>Ce que le nettoyage a corrigé ou écarté lors du dernier traitement{{ qualite?.date ? ' (' + (qualite.date | date:'d MMM y, HH:mm') + ')' : '' }}.
          Les champs incohérents sont vidés plutôt que de supprimer l'annonce.</p>
      </div>
      <div class="card" *ngIf="qualiteLignes.length; else qualiteVide">
        <div class="qualite-entonnoir">
          <div *ngFor="let c of qualiteColonnes" class="qualite-seg">
            <span class="qualite-seg-nom"><span class="pastille" [style.background]="c.couleur"></span>{{ c.libelle }}</span>
            <strong>{{ c.propres | number }}</strong> <span class="muted">annonces retenues sur {{ c.brutes | number }} collectées</span>
            <div class="qualite-barre"><span [style.width.%]="c.part" [style.background]="c.couleur"></span></div>
          </div>
        </div>
        <div class="table-wrap">
          <table class="qualite-table">
            <thead><tr><th>Contrôle</th><th *ngFor="let c of qualiteColonnes">{{ c.libelle }}</th></tr></thead>
            <tbody>
              <tr *ngFor="let l of qualiteLignes">
                <td>{{ l.libelle }}<div class="muted small" *ngIf="l.aide">{{ l.aide }}</div></td>
                <td *ngFor="let v of l.valeurs">{{ v === null ? '—' : (v | number) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <ng-template #qualiteVide><div class="card muted">Aucun rapport de qualité disponible pour le moment.</div></ng-template>
    </section>
  `,
  styles: []
})
export class StatsComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChildren('canvas') canvases!: QueryList<ElementRef<HTMLCanvasElement>>;

  stats: any = null;
  marche: any = null;
  // Calculé une seule fois : un getter renvoyant de nouveaux objets à chaque
  // détection de changements faisait reconstruire le *ngFor en boucle
  // (re-layout -> resize Chart.js -> nouvelle détection), jusqu'au crash de l'onglet.
  collections: any[] = [];
  kpis: { libelle: string; valeur: string; aide?: string }[] = [];

  sections = [
    { id: 'regions', titre: 'Par région', description: 'Chaque annonce est rattachée à sa région (Grand Tunis, Cap Bon, Sahel…) à partir de sa ville ou de son gouvernorat. Médianes affichées à partir de 8 annonces.' },
    { id: 'vente', titre: 'Vente', description: 'Niveau des prix à l\'achat selon la localisation.' },
    { id: 'location', titre: 'Location à l\'année', description: 'Loyers mensuels observés dans les annonces.' },
    { id: 'taille', titre: 'Selon la taille du bien', description: 'Prix médian par nombre de chambres (S+n), un graphique par segment car les échelles diffèrent.' },
    { id: 'estival', titre: 'Location estivale', description: 'Prix par nuit des logements entiers (Booking).' },
    { id: 'investissement', titre: 'Investissement', description: 'Rendement locatif brut estimé à partir des médianes de prix et de loyer.' },
    { id: 'activite', titre: 'Activité et données', description: 'Rythme de collecte, composition des annonces et variations de prix.' },
  ];

  graphiques: Graphique[] = [
    this.g('regionVolumes', 'regions', 'Annonces par région', 'Nombre d\'annonces par segment', true),
    this.g('regionM2', 'regions', 'Prix médian au m² par région', 'Vente, TND/m²'),
    this.g('regionLoyer', 'regions', 'Loyer médian par région', 'Location à l\'année, TND/mois'),
    this.g('regionPrix', 'regions', 'Prix médian de vente par région', 'Vente, prix total (TND) : reflète aussi la taille des biens', true),
    this.g('regionNuit', 'regions', 'Prix médian par nuit par région', 'Location estivale, TND/nuit', true),
    this.g('prixm2Gouv', 'vente', 'Prix médian au m² par gouvernorat', 'TND/m², gouvernorats avec au moins 8 annonces'),
    this.g('histoM2', 'vente', 'Distribution des prix au m²', 'Nombre d\'annonces de vente par tranche de prix au m²'),
    this.g('prixGouv', 'vente', 'Prix médian par zone', 'Prix total (TND), toutes surfaces confondues'),
    this.g('loyerVille', 'location', 'Loyer médian par ville', 'TND/mois, 12 villes les plus chères (au moins 8 annonces)', true),
    this.g('chambresVente', 'taille', 'Vente', 'Prix médian (TND)'),
    this.g('chambresLocation', 'taille', 'Location', 'Loyer médian (TND/mois)'),
    this.g('chambresEstival', 'taille', 'Estival', 'Prix médian (TND/nuit)'),
    this.g('nuitVille', 'estival', 'Prix médian par nuit par ville', 'TND/nuit'),
    this.g('nuitType', 'estival', 'Prix médian par nuit selon le logement', 'TND/nuit'),
    this.g('rendement', 'investissement', 'Rendement locatif brut par ville', '', true),
    this.g('activite', 'activite', 'Nouvelles annonces par jour', '60 derniers jours, par segment', true),
    this.g('types', 'activite', 'Répartition par type de bien', 'Part des annonces de chaque segment'),
    this.g('sources', 'activite', 'Provenance des données', 'Part de chaque site source dans les annonces (%)'),
    this.g('variations', 'activite', 'Variations de prix récentes', 'Plus fortes variations sur 90 jours (%)', true),
  ];

  private charts = new Map<string, Chart>();

  qualite: any = null;
  qualiteColonnes: { libelle: string; couleur: string; brutes: number; propres: number; part: number }[] = [];
  qualiteLignes: { libelle: string; aide?: string; valeurs: (number | null)[] }[] = [];

  constructor(private http: HttpClient) {}

  private g(id: string, section: string, titre: string, aide = '', large = false): Graphique {
    return { id, section, titre, aide, large, config: null, tableau: null, voirTableau: false };
  }

  parSection(section: string): Graphique[] {
    return this.graphiques.filter(g => g.section === section);
  }

  ngOnInit(): void {
    const sur = (obs: any) => obs.pipe(catchError(() => of(null)));
    forkJoin({
      stats: sur(this.http.get<any>(API_BASE + '/api/stats')),
      marche: sur(this.http.get<any>(API_BASE + '/api/stats/marche')),
      gouv: sur(this.http.get<any>(API_BASE + '/api/stats/prix_par_gouvernorat?collection=clean_vente')),
      villes: sur(this.http.get<any>(API_BASE + '/api/stats/prix_par_ville?collection=clean_estival')),
      qualite: sur(this.http.get<any>(API_BASE + '/api/stats/qualite')),
      variations: forkJoin(['clean_vente', 'clean_location', 'clean_estival'].map(collection =>
        this.http.get<any>(API_BASE + '/api/alertes/prix', { params: { collection, jours: 90, limit: 200 } })
          .pipe(catchError(() => of({ data: [] }))))),
    }).subscribe((r: any) => {
      this.stats = r.stats;
      this.marche = r.marche;
      this.collections = Object.keys(r.stats?.collections || {}).map(key => ({ name: key, ...r.stats.collections[key] }));
      this.construireKpis();
      this.construireQualite(r.qualite);
      this.construireGraphiques(r);
      setTimeout(() => this.dessiner());
    });
  }

  ngAfterViewInit(): void {
    this.canvases.changes.subscribe(() => this.dessiner());
  }

  ngOnDestroy(): void {
    this.charts.forEach(c => c.destroy());
    this.charts.clear();
  }

  allerA(id: string): void {
    document.getElementById('stats-' + id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  private construireQualite(rapport: any): void {
    const cols = rapport?.collections;
    if (!cols) return;
    this.qualite = rapport;
    const segments = (['vente', 'location', 'estival'] as const).filter(seg => cols[`clean_${seg}`]);
    this.qualiteColonnes = segments.map(seg => {
      const c = cols[`clean_${seg}`];
      return { libelle: LIBELLE_SEGMENT[seg], couleur: SEGMENT[seg], brutes: c.annonces_brutes ?? 0, propres: c.annonces_propres ?? 0,
               part: c.annonces_brutes ? Math.round(100 * (c.annonces_propres ?? 0) / c.annonces_brutes) : 0 };
    });
    const controles: [string, string, string?][] = [
      ['non_residentiels_retires', 'Biens non résidentiels écartés', 'terrains, locaux, bureaux…'],
      ['locations_mal_classees_retirees', 'Locations publiées en vente', 'reclassées hors du segment vente'],
      ['prix_hors_norme_retires', 'Prix hors norme écartés'],
      ['chambres_hotel_retirees', 'Chambres d\'hôtel écartées', 'seuls les logements entiers sont gardés'],
      ['annonces_retirees_exclues', 'Annonces retirées du site'],
      ['doublons_meme_bien_retires', 'Doublons (même bien, plusieurs annonces)'],
      ['doublons_texte_retires', 'Doublons (texte quasi identique)'],
      ['chambres_aberrantes_corrigees', 'Nombre de chambres corrigé', 'valeur incohérente, reprise du titre (S+n)'],
      ['chambres_completees_depuis_titre', 'Chambres complétées depuis le titre'],
      ['surfaces_incoherentes_videes', 'Surfaces incohérentes vidées', 'prix au m² impossible'],
      ['pieces_aberrantes_videes', 'Nombre de pièces aberrant vidé'],
      ['sans_surface', 'Annonces sans surface', 'restent utilisables, hors calculs au m²'],
      ['sans_coordonnees', 'Annonces non géolocalisées'],
    ];
    this.qualiteLignes = controles
      .map(([cle, libelle, aide]) => ({ libelle, aide, valeurs: segments.map(seg => cols[`clean_${seg}`][cle] ?? null) }))
      .filter(l => l.valeurs.some(v => v));
  }

  labelForCollection(name: string): string {
    if (name === 'vente') return 'Vente';
    if (name === 'estival') return 'Location estivale';
    return 'Location';
  }

  private construireKpis(): void {
    const m = this.marche?.kpis || {};
    const med = (c: string) => this.stats?.prix_median?.[c]?.median;
    const tnd = (v: any, suffixe = 'TND') => (v || v === 0) ? `${nf(v)} ${suffixe}` : '—';
    this.kpis = [
      { libelle: 'Total annonces', valeur: this.stats?.total_annonces ? nf(this.stats.total_annonces) : '—' },
      { libelle: 'Prix médian vente', valeur: tnd(med('clean_vente')) },
      { libelle: 'Prix médian au m²', valeur: tnd(m.prix_m2_median_vente, 'TND/m²'), aide: 'vente' },
      { libelle: 'Loyer médian', valeur: tnd(med('clean_location'), 'TND/mois') },
      { libelle: 'Loyer médian au m²', valeur: tnd(m.loyer_m2_median, 'TND/m²'), aide: 'par mois' },
      { libelle: 'Prix médian par nuit', valeur: tnd(m.prix_nuit_median), aide: 'location estivale' },
      { libelle: 'Rendement brut médian', valeur: m.rendement_brut_median_pct ? `${nf(m.rendement_brut_median_pct, 1)} %` : '—', aide: 'appartements, avant charges' },
      { libelle: 'Opportunités détectées', valeur: m.opportunites !== undefined ? nf(m.opportunites) : '—', aide: 'prix nettement sous l\'estimation' },
    ];
  }

  private def(id: string): Graphique {
    return this.graphiques.find(g => g.id === id)!;
  }

  private barres(id: string, lignes: { label: string; valeur: number }[], couleur: string, unite: string,
                 options: { horizontal?: boolean; colonnes?: string[]; tableau?: (string | number)[][] } = {}): void {
    const g = this.def(id);
    if (!lignes.length) { g.vide = g.vide || 'Pas assez de données'; return; }
    const horizontal = !!options.horizontal;
    g.config = {
      type: 'bar',
      data: {
        labels: lignes.map(l => l.label),
        datasets: [{
          label: g.titre,
          data: lignes.map(l => l.valeur),
          backgroundColor: couleur,
          borderRadius: 4,
          borderSkipped: 'start',
          maxBarThickness: 34,
        }],
      },
      options: {
        indexAxis: horizontal ? 'y' : 'x',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx: any) => ` ${nf(ctx.raw)} ${unite}` } },
        },
        scales: this.axes(horizontal, (v: any) => nf(v)),
      },
    } as ChartConfiguration;
    g.tableau = {
      colonnes: options.colonnes || ['', unite],
      lignes: options.tableau || lignes.map(l => [l.label, nf(l.valeur)]),
    };
  }

  private axes(horizontal: boolean, format: (v: any) => string): any {
    const valeurs = { grid: { color: GRILLE }, border: { display: false }, ticks: { color: ENCRE, callback: format } };
    const categories = { grid: { display: false }, border: { display: false }, ticks: { color: ENCRE, autoSkip: false, maxRotation: 45 } };
    return horizontal ? { x: valeurs, y: categories } : { x: categories, y: valeurs };
  }

  private construireGraphiques(r: any): void {
    const m = r.marche || {};
    if (!r.marche) {
      // API lancée avant l'ajout de /api/stats/marche (404) ou injoignable
      const message = "Données momentanément indisponibles.";
      ['regionVolumes', 'regionM2', 'regionLoyer', 'regionPrix', 'regionNuit', 'prixm2Gouv', 'histoM2', 'loyerVille', 'chambresVente', 'chambresLocation', 'chambresEstival', 'nuitType',
       'rendement', 'activite', 'types'].forEach(id => this.def(id).vide = message);
    }

    this.barres('prixm2Gouv', (m.vente_prix_m2_par_gouvernorat || []).map((z: any) => ({ label: z.cle, valeur: z.median })),
      SEGMENT.vente, 'TND/m²', {
        colonnes: ['Gouvernorat', 'Prix médian au m²', 'Annonces'],
        tableau: (m.vente_prix_m2_par_gouvernorat || []).map((z: any) => [z.cle, `${nf(z.median)} TND/m²`, z.n]),
      });

    this.barres('histoM2', (m.vente_histogramme_prix_m2 || []).map((h: any) => ({ label: h.tranche, valeur: h.n })),
      SEGMENT.vente, 'annonces', { colonnes: ['Prix au m² (TND)', 'Annonces'] });
    const histo = this.def('histoM2').config as any;
    if (histo) {
      // Histogramme : barres jointives
      histo.data.datasets[0].barPercentage = 1;
      histo.data.datasets[0].categoryPercentage = 0.96;
      histo.options.plugins.tooltip.callbacks.title = (items: any[]) => `${items[0].label} TND/m²`;
    }

    const gouv = (r.gouv?.data || []).filter((z: any) => z._id && z.prix_median && z.count >= 8).slice(0, 10);
    this.barres('prixGouv', gouv.map((z: any) => ({ label: z._id, valeur: z.prix_median })), SEGMENT.vente, 'TND', {
      colonnes: ['Zone', 'Prix médian', 'Annonces'],
      tableau: gouv.map((z: any) => [z._id, `${nf(z.prix_median)} TND`, z.count]),
    });

    this.barres('loyerVille', (m.location_loyer_par_ville || []).map((z: any) => ({ label: z.cle, valeur: z.median })),
      SEGMENT.location, 'TND/mois', {
        horizontal: true,
        colonnes: ['Ville', 'Loyer médian', 'Annonces'],
        tableau: (m.location_loyer_par_ville || []).map((z: any) => [z.cle, `${nf(z.median)} TND/mois`, z.n]),
      });

    const chambres = m.prix_par_chambres || {};
    ([['chambresVente', 'vente', 'TND'], ['chambresLocation', 'location', 'TND/mois'], ['chambresEstival', 'estival', 'TND/nuit']] as const)
      .forEach(([id, seg, unite]) => this.barres(id, (chambres[seg] || []).map((c: any) => ({ label: c.cle, valeur: c.median })),
        SEGMENT[seg], unite, {
          colonnes: ['Chambres', 'Prix médian', 'Annonces'],
          tableau: (chambres[seg] || []).map((c: any) => [c.cle, `${nf(c.median)} ${unite}`, c.n]),
        }));

    const villes = (r.villes?.data || []).filter((z: any) => z._id && z.prix_median && z.count >= 8)
      .sort((a: any, b: any) => b.prix_median - a.prix_median).slice(0, 12);
    this.barres('nuitVille', villes.map((z: any) => ({ label: z._id, valeur: z.prix_median })), SEGMENT.estival, 'TND/nuit', {
      colonnes: ['Ville', 'Prix médian / nuit', 'Logements'],
      tableau: villes.map((z: any) => [z._id, `${nf(z.prix_median)} TND`, z.count]),
    });

    this.barres('nuitType', (m.estival_par_type || []).map((t: any) => ({ label: LIBELLE_TYPE[t.cle] || t.cle, valeur: t.median })),
      SEGMENT.estival, 'TND/nuit', {
        colonnes: ['Logement', 'Prix médian / nuit', 'Logements'],
        tableau: (m.estival_par_type || []).map((t: any) => [LIBELLE_TYPE[t.cle] || t.cle, `${nf(t.median)} TND`, t.n]),
      });

    const rendements = m.rendement_par_ville || [];
    this.def('rendement').aide = m.note_rendement || '';
    this.barres('rendement', rendements.map((z: any) => ({ label: z.ville, valeur: z.rendement_brut_pct })), NEUTRE, '%', {
      horizontal: true,
      colonnes: ['Ville', 'Rendement brut', 'Prix médian', 'Loyer médian', 'Annonces vente / location'],
      tableau: rendements.map((z: any) => [z.ville, `${nf(z.rendement_brut_pct, 1)} %`, `${nf(z.prix_median)} TND`,
        `${nf(z.loyer_median)} TND/mois`, `${z.n_vente} / ${z.n_location}`]),
    });
    const rend = this.def('rendement').config as any;
    if (rend) {
      rend.options.plugins.tooltip.callbacks.label = (ctx: any) => {
        const z = rendements[ctx.dataIndex];
        return ` ${nf(z.rendement_brut_pct, 1)} % (loyer ${nf(z.loyer_median)} TND/mois, prix ${nf(z.prix_median)} TND)`;
      };
      rend.options.scales.x.ticks.callback = (v: any) => `${v} %`;
    }

    this.activite(m.activite_quotidienne || []);
    this.typesBiens(m.types || {});

    this.regions(m.par_region || []);
    this.sources(r.stats?.collections || {});

    this.variations((r.variations || []).flatMap((x: any) => x?.data || []));
  }

  private regions(regions: any[]): void {
    const g = this.def('regionVolumes');
    if (regions.length) {
      const segments = ['vente', 'location', 'estival'] as const;
      g.config = {
        type: 'bar',
        data: {
          labels: regions.map(z => z.region),
          datasets: segments.map(seg => ({
            label: LIBELLE_SEGMENT[seg],
            data: regions.map(z => z[`n_${seg}`]),
            backgroundColor: SEGMENT[seg],
            borderColor: '#ffffff',
            borderWidth: 1,
            stack: 'region',
          })),
        },
        options: {
          indexAxis: 'y',
          plugins: {
            legend: { position: 'bottom', labels: { color: ENCRE, boxWidth: 12, boxHeight: 12 } },
            tooltip: { mode: 'index', intersect: false },
          },
          scales: {
            x: { stacked: true, grid: { color: GRILLE }, border: { display: false }, ticks: { color: ENCRE } },
            y: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: ENCRE } },
          },
        },
      } as ChartConfiguration;
      g.tableau = {
        colonnes: ['Région', 'Vente', 'Location', 'Estival', 'Prix médian vente', 'Prix au m²', 'Loyer médian', 'Prix / nuit'],
        lignes: regions.map(z => [z.region, z.n_vente, z.n_location, z.n_estival,
          z.prix_vente ? `${nf(z.prix_vente)} TND` : '—', z.prix_m2_vente ? `${nf(z.prix_m2_vente)} TND/m²` : '—',
          z.loyer ? `${nf(z.loyer)} TND/mois` : '—', z.prix_nuit ? `${nf(z.prix_nuit)} TND` : '—']),
      };
    } else {
      g.vide = g.vide || 'Pas de données';
    }

    // Médianes : régions classées de la plus chère à la moins chère, sans les régions trop peu fournies
    const classement = (cle: string, seg: string) => regions.filter(z => z[cle])
      .sort((a, b) => b[cle] - a[cle])
      .map(z => ({ region: z.region, valeur: z[cle], n: z[`n_${seg}`] }));
    ([['regionM2', 'prix_m2_vente', 'vente', 'TND/m²'], ['regionLoyer', 'loyer', 'location', 'TND/mois'],
      ['regionPrix', 'prix_vente', 'vente', 'TND'],
      ['regionNuit', 'prix_nuit', 'estival', 'TND/nuit']] as const).forEach(([id, cle, seg, unite]) => {
      const lignes = classement(cle, seg);
      this.barres(id, lignes.map(l => ({ label: l.region, valeur: l.valeur })), SEGMENT[seg], unite, {
        horizontal: true,
        colonnes: ['Région', 'Médiane', 'Annonces'],
        tableau: lignes.map(l => [l.region, `${nf(l.valeur)} ${unite}`, l.n]),
      });
    });
  }

  private sources(collections: any): void {
    const g = this.def('sources');
    const parSegment = (['vente', 'location', 'estival'] as const)
      .filter(seg => collections[seg]?.top_sources?.length)
      .map(seg => ({
        libelle: LIBELLE_SEGMENT[seg],
        comptes: Object.fromEntries(collections[seg].top_sources.map((t: any) => [String(t.source).toLowerCase(), Number(t.count)])) as Record<string, number>,
      }));
    if (!parSegment.length) { g.vide = g.vide || 'Pas de données'; return; }
    const total: Record<string, number> = {};
    parSegment.forEach(l => Object.entries(l.comptes).forEach(([src, n]) => total[src] = (total[src] || 0) + n));
    const lignes = [{ libelle: 'Toutes les annonces', comptes: total }, ...parSegment];
    const connues = Object.keys(SOURCE).filter(src => total[src]);
    const sources = [...connues, ...Object.keys(total).filter(src => !SOURCE[src]).sort((a, b) => total[b] - total[a])];
    const somme = (c: Record<string, number>) => Object.values(c).reduce((a, b) => a + b, 0);
    const part = (c: Record<string, number>, src: string) => somme(c) ? Math.round((c[src] || 0) / somme(c) * 1000) / 10 : 0;
    const nom = (src: string) => src.charAt(0).toUpperCase() + src.slice(1);

    g.config = {
      type: 'bar',
      data: {
        labels: lignes.map(l => l.libelle),
        datasets: sources.map(src => ({
          label: nom(src),
          data: lignes.map(l => part(l.comptes, src)),
          backgroundColor: SOURCE[src] || AUTRE_SOURCE,
          borderColor: '#ffffff',
          borderWidth: 2,
          stack: 'part',
        })),
      },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { position: 'bottom', labels: { color: ENCRE, boxWidth: 12, boxHeight: 12 } },
          tooltip: { callbacks: { label: (ctx: any) => ` ${ctx.dataset.label} : ${nf(ctx.raw, 1)} % (${nf(lignes[ctx.dataIndex].comptes[sources[ctx.datasetIndex]] || 0)} annonces)` } },
        },
        scales: {
          x: { stacked: true, max: 100, grid: { color: GRILLE }, border: { display: false }, ticks: { color: ENCRE, callback: (v: any) => `${v} %` } },
          y: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: ENCRE } },
        },
      },
      plugins: [etiquettesSegments],
    } as ChartConfiguration;
    g.tableau = {
      colonnes: ['', ...sources.map(nom)],
      lignes: lignes.map(l => [l.libelle, ...sources.map(src => l.comptes[src] ? `${nf(l.comptes[src])} (${nf(part(l.comptes, src), 1)} %)` : '—')]),
    };
  }

  private activite(jours: any[]): void {
    const g = this.def('activite');
    if (!jours.some(j => j.vente || j.location || j.estival)) { g.vide = g.vide || 'Aucune nouvelle annonce sur la période'; return; }
    const libelle = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
    g.config = {
      type: 'bar',
      data: {
        labels: jours.map(j => libelle(j.date)),
        datasets: (['vente', 'location', 'estival'] as const).map(seg => ({
          label: LIBELLE_SEGMENT[seg],
          data: jours.map(j => j[seg]),
          backgroundColor: SEGMENT[seg],
          borderColor: '#ffffff',
          borderWidth: 1,
          stack: 'jour',
        })),
      },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { color: ENCRE, boxWidth: 12, boxHeight: 12 } },
          tooltip: { mode: 'index', intersect: false },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: ENCRE, maxTicksLimit: 12 } },
          y: { stacked: true, grid: { color: GRILLE }, border: { display: false }, ticks: { color: ENCRE } },
        },
      },
    } as ChartConfiguration;
    g.tableau = {
      colonnes: ['Date', 'Vente', 'Location', 'Estival'],
      lignes: jours.filter(j => j.vente || j.location || j.estival).reverse()
        .map(j => [libelle(j.date), j.vente, j.location, j.estival]),
    };
  }

  private typesBiens(types: any): void {
    const g = this.def('types');
    const segments = ['vente', 'location', 'estival'].filter(s => Object.keys(types[s] || {}).length);
    if (!segments.length) { g.vide = g.vide || 'Pas de données'; return; }
    const tous = ['appartement', 'villa', 'maison_vacances'];
    const total = (s: string) => Object.values(types[s] || {}).reduce((a: number, b: any) => a + Number(b), 0) as number;
    const part = (s: string, t: string) => total(s) ? Math.round((types[s]?.[t] || 0) / total(s) * 1000) / 10 : 0;
    g.config = {
      type: 'bar',
      data: {
        labels: segments.map(s => LIBELLE_SEGMENT[s]),
        datasets: tous.filter(t => segments.some(s => types[s]?.[t])).map(t => ({
          label: LIBELLE_TYPE[t],
          data: segments.map(s => part(s, t)),
          backgroundColor: TYPE_BIEN[t],
          borderColor: '#ffffff',
          borderWidth: 2,
          stack: 'part',
        })),
      },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { position: 'bottom', labels: { color: ENCRE, boxWidth: 12, boxHeight: 12 } },
          tooltip: { callbacks: { label: (ctx: any) => ` ${ctx.dataset.label} : ${nf(ctx.raw, 1)} %` } },
        },
        scales: {
          x: { stacked: true, max: 100, grid: { color: GRILLE }, border: { display: false }, ticks: { color: ENCRE, callback: (v: any) => `${v} %` } },
          y: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: ENCRE } },
        },
      },
    } as ChartConfiguration;
    g.tableau = {
      colonnes: ['Segment', ...tous.map(t => LIBELLE_TYPE[t])],
      lignes: segments.map(s => [LIBELLE_SEGMENT[s], ...tous.map(t => types[s]?.[t] ? `${types[s][t]} (${nf(part(s, t), 1)} %)` : '—')]),
    };
  }

  private variations(liste: any[]): void {
    const g = this.def('variations');
    const top = [...liste].sort((a, b) => Math.abs(b.variation_pct) - Math.abs(a.variation_pct)).slice(0, 10);
    if (!top.length) { g.vide = 'Aucune variation de prix détectée sur 90 jours'; return; }
    const court = (t: string) => (t || 'Annonce').length > 26 ? (t || 'Annonce').slice(0, 25) + '…' : (t || 'Annonce');
    // Le signe est porté par la direction de la barre (gauche = baisse, droite = hausse)
    this.barres('variations', top.map(v => ({ label: court(v.titre), valeur: v.variation_pct })), NEUTRE, '%', {
      horizontal: true,
      colonnes: ['Annonce', 'Ancien prix', 'Nouveau prix', 'Variation'],
      tableau: top.map(v => [v.titre || 'Annonce', nf(v.ancien_prix), nf(v.nouveau_prix), `${v.variation_pct > 0 ? '+' : ''}${nf(v.variation_pct, 1)} %`]),
    });
    const cfg = g.config as any;
    cfg.options.plugins.tooltip.callbacks.label = (ctx: any) => {
      const v = top[ctx.dataIndex];
      return ` ${v.variation_pct > 0 ? '+' : ''}${nf(v.variation_pct, 1)} % (${nf(v.ancien_prix)} → ${nf(v.nouveau_prix)})`;
    };
    cfg.options.scales.x.ticks.callback = (v: any) => `${v} %`;
  }

  private dessiner(): void {
    this.canvases?.forEach(ref => {
      const canvas = ref.nativeElement;
      const id = canvas.dataset['id'] as string;
      const g = this.graphiques.find(x => x.id === id);
      if (!g?.config || this.charts.get(id)?.canvas === canvas) return;
      this.charts.get(id)?.destroy();
      // Hauteur fixée par .chart-box : sans maintainAspectRatio=false, le canvas
      // responsive et son conteneur se redimensionnent mutuellement en boucle
      const config = { ...g.config, options: { ...(g.config.options || {}), responsive: true, maintainAspectRatio: false } } as ChartConfiguration;
      this.charts.set(id, new Chart(canvas, config));
    });
  }
}
