import { Component, OnInit, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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
          <h2>Vue consolidée des volumes, des prix et de la qualité des données</h2>
          <p class="section-copy">
            Les indicateurs ci-dessous mettent en avant la couverture GPS, les prix centraux et le niveau de fiabilité des lots nettoyés.
          </p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ stats?.global_geo_coverage_pct ?? '—' }}%</strong> couverture GPS</div>
          <div class="summary-pill"><strong>{{ historyCount }}</strong> annonces historisées</div>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-tile">
          <span>Total annonces</span>
          <strong>{{ stats?.total_annonces || '—' }}</strong>
        </div>
        <div class="summary-tile">
          <span>Prix médian vente</span>
          <strong>{{ stats?.prix_median?.clean_vente?.median ? (stats.prix_median.clean_vente.median | number:'1.0-0') : '—' }}</strong>
        </div>
        <div class="summary-tile">
          <span>Prix moyen / nuit</span>
          <strong>{{ stats?.prix_moyen?.clean_estival ? (stats.prix_moyen.clean_estival | number:'1.0-0') : '—' }}</strong>
        </div>
        <div class="summary-tile">
          <span>Couverture GPS</span>
          <strong>{{ stats?.global_geo_coverage_pct ?? '—' }}%</strong>
        </div>
      </div>

      <div class="stats-grid">
        <div class="card stat-card total">
          <div class="stat-value">{{ stats?.total_annonces || '—' }}</div>
          <div class="stat-label">Total annonces</div>
          <div class="stat-sub">Toutes collections</div>
        </div>
        <div class="card stat-card vente" *ngFor="let item of collections">
          <div class="stat-value">{{ item.total }}</div>
          <div class="stat-label">{{ labelForCollection(item.name) }}</div>
          <div class="stat-sub">
            {{ item.nouveaux_7j }} nouveaux · {{ item.couverture_gps_pct }}% GPS · qualité {{ item.qualite_moyenne ?? '—' }}/100
          </div>
        </div>
        <div class="card stat-card vente">
          <div class="stat-value">{{ stats?.prix_moyen?.clean_vente ? (stats.prix_moyen.clean_vente | number:'1.0-0') : '—' }}</div>
          <div class="stat-label">Prix moyen vente</div>
          <div class="stat-sub">TND</div>
        </div>
        <div class="card stat-card estival">
          <div class="stat-value">{{ stats?.prix_median?.clean_estival?.median ? (stats.prix_median.clean_estival.median | number:'1.0-0') : '—' }}</div>
          <div class="stat-label">Prix médian / nuit</div>
          <div class="stat-sub">TND</div>
        </div>
      </div>
    </div>

    <div class="charts-grid">
      <div class="card chart-card">
        <h3>Prix moyen par gouvernorat — Vente (TND)</h3>
        <canvas #govCanvas></canvas>
      </div>
      <div class="card chart-card">
        <h3>Prix / nuit par ville — Estival (TND)</h3>
        <canvas #cityCanvas></canvas>
      </div>
      <div class="card chart-card">
        <h3>Sources des annonces</h3>
        <canvas #srcCanvas></canvas>
      </div>
      <div class="card chart-card">
        <h3>Évolution des prix par ville (historique)</h3>
        <canvas #histCanvas></canvas>
        <p style="font-size:0.75rem;color:var(--text-light);margin-top:6px">
          Basé sur l'historique {{ historyCount }} annonces avec price_history
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
    this.http.get<any>('http://localhost:8000/api/stats').subscribe(data => {
      this.stats = data;
      if (this.srcCanvas && data?.sources) {
        this.renderSourceChart(data.sources);
      }
    });
    this.http.get<any>('http://localhost:8000/api/stats/prix_par_gouvernorat?collection=clean_vente')
      .subscribe(d => this.renderGovChart(d.data));
    this.http.get<any>('http://localhost:8000/api/stats/prix_par_ville?collection=clean_estival')
      .subscribe(d => this.renderCityChart(d.data));
  }

  ngAfterViewInit(): void {
    this.http.get<any>('http://localhost:8000/api/annonces/?limit=10&sort=-scraped_at')
      .subscribe(res => this.renderHistChart(res.data));
    if (this.stats?.sources && this.srcCanvas) {
      this.renderSourceChart(this.stats.sources);
    }
  }

  ngOnDestroy(): void {
    this.chartInstances.forEach(chart => chart.destroy());
    this.chartInstances = [];
  }

  get collections(): any[] {
    if (!this.stats?.collections) return [];
    return Object.keys(this.stats.collections).map(key => ({
      name: key,
      ...this.stats.collections[key]
    }));
  }

  labelForCollection(name: string): string {
    if (name === 'vente') return 'Vente';
    if (name === 'estival') return 'Location estivale';
    return 'Location';
  }

  private renderGovChart(rows: any[]): void {
    const rowsSane = (rows || []).filter(r => r._id && r.prix_moyen).slice(0, 8);
    if (!rowsSane.length || !this.govCanvas) return;
    this.renderChart(this.govCanvas.nativeElement, 'bar', {
      labels: rowsSane.map(r => r._id),
      datasets: [{
        label: 'Prix moyen (TND)',
        data: rowsSane.map(r => r.prix_moyen),
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
    const rowsSane = (rows || []).filter(r => r._id && r.prix_moyen).slice(0, 8);
    if (!rowsSane.length || !this.cityCanvas) return;
    this.renderChart(this.cityCanvas.nativeElement, 'bar', {
      labels: rowsSane.map(r => r._id),
      datasets: [{
        label: 'Prix / nuit (TND)',
        data: rowsSane.map(r => r.prix_moyen),
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

  private renderHistChart(annonces: any[]): void {
    const withHist = (annonces || [])
      .filter(a => a.price_history && a.price_history.length > 1)
      .slice(0, 4);

    this.historyCount = withHist.length;
    if (!withHist.length || !this.histCanvas) return;

    const fmt = (iso: string) => iso ? iso.slice(5, 10).replace('-', '/') : '';
    const series = withHist.map(a => ({
      label: (a.titre || 'Annonce').slice(0, 24),
      labels: (a.price_history || []).slice(-8).map((h: any) => fmt(h.date)),
      data: (a.price_history || []).slice(-8).map((h: any) => h.prix)
    }));

    const allLabels = [...new Set(series.flatMap(s => s.labels))].sort().slice(-8);

    this.renderChart(this.histCanvas.nativeElement, 'line', {
      labels: allLabels,
      datasets: series.map((s, i) => ({
        label: s.label,
        data: allLabels.map(l => {
          const idx = s.labels.indexOf(l);
          return idx >= 0 ? s.data[idx] : null;
        }),
        borderColor: ['#1a237e', '#00bcd4', '#e65100', '#2e7d32'][i % 4],
        fill: false,
        tension: 0.2,
        spanGaps: true,
      }))
    }, {
      responsive: true,
      plugins: { legend: { position: 'bottom' } },
      scales: {
        y: { ticks: { callback: (v: any) => Number(v).toLocaleString() } }
      }
    });
  }

  private renderChart(canvas: HTMLCanvasElement, type: any, data: any, options: any): void {
    if (!canvas) return;
    this.chartInstances.forEach(chart => chart.destroy());
    this.chartInstances = [];
    const chart = new Chart(canvas, { type, data, options });
    this.chartInstances.push(chart);
  }
}
