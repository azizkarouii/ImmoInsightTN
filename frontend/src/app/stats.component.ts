import { API_BASE } from './api.config';
import { Component, OnInit, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { CommonModule } from '@angular/common';
import Chart from 'chart.js/auto';

@Component({
  selector: 'app-stats',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card" style="margin-bottom:20px">
      <div class="section-head">
        <div>
          <p class="eyebrow">Lecture du marché</p>
          <h2>Volumes, prix et qualité des données</h2>
          <p class="section-copy">
            Prix médians (moins sensibles aux biens de luxe que les moyennes), couverture GPS et qualité des lots nettoyés.
          </p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ stats?.global_geo_coverage_pct ?? '—' }}%</strong> couverture GPS</div>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-tile">
          <span>Total annonces</span>
          <strong>{{ stats?.total_annonces ? (stats.total_annonces | number) : '—' }}</strong>
        </div>
        <div class="summary-tile">
          <span>Prix médian vente</span>
          <strong>{{ median('clean_vente') }}</strong>
        </div>
        <div class="summary-tile">
          <span>Loyer médian / mois</span>
          <strong>{{ median('clean_location') }}</strong>
        </div>
        <div class="summary-tile">
          <span>Prix médian / nuit</span>
          <strong>{{ median('clean_estival') }}</strong>
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

    <div class="charts-grid">
      <div class="card chart-card">
        <h3>Prix médian par gouvernorat — Vente (TND)</h3>
        <div class="chart-box"><canvas #govCanvas></canvas></div>
      </div>
      <div class="card chart-card">
        <h3>Prix médian / nuit par ville — Estival (TND)</h3>
        <div class="chart-box"><canvas #cityCanvas></canvas></div>
      </div>
      <div class="card chart-card">
        <h3>Sources des annonces</h3>
        <div class="chart-box"><canvas #srcCanvas></canvas></div>
      </div>
      <div class="card chart-card">
        <h3>Variations de prix récentes (90 j)</h3>
        <div class="chart-box"><canvas #histCanvas></canvas></div>
        <p style="font-size:0.75rem;color:var(--text-light);margin-top:6px">
          {{ historyCount }} annonce(s) dont le prix a changé entre deux passages des scrapers
        </p>
      </div>
    </div>
  `,
  styles: []
})
export class StatsComponent implements OnInit, AfterViewInit {
  @ViewChild('govCanvas') govCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('cityCanvas') cityCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('srcCanvas') srcCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('histCanvas') histCanvas!: ElementRef<HTMLCanvasElement>;

  stats: any = null;
  historyCount = 0;
  private chartInstances: Chart[] = [];

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<any>(API_BASE + '/api/stats').subscribe(data => {
      this.stats = data;
      this.collections = Object.keys(data?.collections || {}).map(key => ({
        name: key,
        ...data.collections[key]
      }));
      if (this.srcCanvas && data?.sources) {
        this.renderSourceChart(data.sources);
      }
    });
    this.http.get<any>(API_BASE + '/api/stats/prix_par_gouvernorat?collection=clean_vente')
      .subscribe(d => this.renderGovChart(d.data));
    this.http.get<any>(API_BASE + '/api/stats/prix_par_ville?collection=clean_estival')
      .subscribe(d => this.renderCityChart(d.data));
  }

  ngAfterViewInit(): void {
    // Variations de prix des trois collections, fusionnées
    forkJoin(['clean_vente', 'clean_location', 'clean_estival'].map(collection =>
      this.http.get<any>(API_BASE + '/api/alertes/prix', { params: { collection, jours: 90, limit: 200 } })
        .pipe(catchError(() => of({ data: [] })))
    )).subscribe(res => this.renderHistChart(res.flatMap(r => r?.data || [])));
    if (this.stats?.sources && this.srcCanvas) {
      this.renderSourceChart(this.stats.sources);
    }
  }

  ngOnDestroy(): void {
    this.chartInstances.forEach(chart => chart.destroy());
    this.chartInstances = [];
  }

  // Calculé une seule fois : un getter renvoyant de nouveaux objets à chaque
  // détection de changements faisait reconstruire le *ngFor en boucle
  // (re-layout -> resize Chart.js -> nouvelle détection), jusqu'au crash de l'onglet.
  collections: any[] = [];

  median(collection: string): string {
    const v = this.stats?.prix_median?.[collection]?.median;
    return v ? Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + ' TND' : '—';
  }

  labelForCollection(name: string): string {
    if (name === 'vente') return 'Vente';
    if (name === 'estival') return 'Location estivale';
    return 'Location';
  }

  private renderGovChart(rows: any[]): void {
    const rowsSane = (rows || []).filter(r => r._id && r.prix_median).slice(0, 10);
    if (!rowsSane.length || !this.govCanvas) return;
    this.renderChart(this.govCanvas.nativeElement, 'bar', {
      labels: rowsSane.map(r => r._id),
      datasets: [{
        label: 'Prix médian (TND)',
        data: rowsSane.map(r => r.prix_median),
        backgroundColor: '#1a237e',
        borderRadius: 4,
      }]
    }, {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { ticks: { callback: (v: any) => Number(v).toLocaleString() } } }
    });
  }

  private renderCityChart(rows: any[]): void {
    const rowsSane = (rows || []).filter(r => r._id && r.prix_median).slice(0, 10);
    if (!rowsSane.length || !this.cityCanvas) return;
    this.renderChart(this.cityCanvas.nativeElement, 'bar', {
      labels: rowsSane.map(r => r._id),
      datasets: [{
        label: 'Prix médian / nuit (TND)',
        data: rowsSane.map(r => r.prix_median),
        backgroundColor: '#00bcd4',
        borderRadius: 4,
      }]
    }, {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { ticks: { callback: (v: any) => Number(v).toLocaleString() } } }
    });
  }

  private renderSourceChart(sources: any): void {
    const merged = new Map<string, number>();
    Object.values(sources || {}).forEach((collectionSources: any) => {
      Object.entries(collectionSources || {}).forEach(([source, count]) => {
        merged.set(source, (merged.get(source) || 0) + Number(count));
      });
    });

    const entries = Array.from(merged.entries())
      .map(([source, count]) => ({ source, count }))
      .filter(item => item.source && item.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);

    if (!entries.length || !this.srcCanvas) return;

    this.renderChart(this.srcCanvas.nativeElement, 'doughnut', {
      labels: entries.map(item => item.source),
      datasets: [{
        data: entries.map(item => item.count),
        backgroundColor: ['#13204a', '#14b8a6', '#2f9e44', '#f59f00', '#e03131'],
        borderWidth: 0,
      }]
    }, {
      responsive: true,
      plugins: { legend: { position: 'bottom' } },
    });
  }

  private renderHistChart(variations: any[]): void {
    // Plus fortes variations (en %) : comparables quel que soit le niveau de prix,
    // contrairement aux courbes de prix absolus
    const top = [...variations]
      .sort((a, b) => Math.abs(b.variation_pct) - Math.abs(a.variation_pct))
      .slice(0, 10);
    this.historyCount = variations.length;
    if (!top.length || !this.histCanvas) return;

    this.renderChart(this.histCanvas.nativeElement, 'bar', {
      labels: top.map(v => { const t = v.titre || 'Annonce'; return t.length > 24 ? t.slice(0, 23) + '…' : t; }),
      datasets: [{
        label: 'Variation (%)',
        data: top.map(v => v.variation_pct),
        backgroundColor: top.map(v => v.variation_pct < 0 ? '#2f9e44' : '#e03131'),
        borderRadius: 4,
      }]
    }, {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx: any) => {
          const v = top[ctx.dataIndex];
          return `${v.variation_pct > 0 ? '+' : ''}${v.variation_pct} % (${Number(v.ancien_prix).toLocaleString('fr-FR')} → ${Number(v.nouveau_prix).toLocaleString('fr-FR')} TND)`;
        } } },
      },
      scales: { x: { ticks: { callback: (v: any) => `${v} %` } } },
    });
  }

  private renderChart(canvas: HTMLCanvasElement, type: any, data: any, options: any): void {
    if (!canvas) return;
    // Ne remplace que le graphique de ce canvas (détruire tous les graphiques
    // ne laissait que le dernier rendu à l'écran)
    Chart.getChart(canvas)?.destroy();
    this.chartInstances = this.chartInstances.filter(chart => chart.canvas !== canvas);
    // Hauteur fixée par .chart-box : sans maintainAspectRatio=false, le canvas
    // responsive et son conteneur se redimensionnent mutuellement en boucle
    const chart = new Chart(canvas, { type, data, options: { ...options, maintainAspectRatio: false } });
    this.chartInstances.push(chart);
  }
}
