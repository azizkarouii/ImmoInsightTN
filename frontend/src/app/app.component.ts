import { Component, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { API_BASE } from './api.config';
import { MapComponent } from './map.component';
import { EstimationComponent } from './estimation.component';
import { StatsComponent } from './stats.component';
import { AlertsComponent } from './alerts.component';
import { ChatWidgetComponent } from './chat-widget.component';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, MapComponent, EstimationComponent, StatsComponent, AlertsComponent, ChatWidgetComponent, IconComponent],
  template: `
    <div class="app-shell">
      <button type="button" class="skip-link" (click)="allerAuContenu()">Aller au contenu</button>
      <header class="app-header">
        <div class="logo">
          <div class="logo-mark"><app-icon name="house"></app-icon></div>
          <div>
            ImmoInsight <span class="logo-tn">TN</span>
            <span class="subtitle">Vente, location et estival en Tunisie</span>
          </div>
        </div>
        <nav class="nav-tabs" aria-label="Sections">
          <button *ngFor="let t of tabs" [class.active]="currentTab === t.id" [attr.aria-current]="currentTab === t.id ? 'page' : null" (click)="ouvrir(t.id)">
            <app-icon [name]="t.icon"></app-icon><span class="nav-label">{{ t.label }}</span>
            <span *ngIf="t.id === 'alertes' && nouveautes24h" class="nav-badge" [attr.aria-label]="nouveautes24h + ' nouvelles annonces en 24 h'">{{ badge(nouveautes24h) }}</span>
          </button>
        </nav>
      </header>

      <main class="main-content" id="contenu" tabindex="-1">
        <div class="status-strip">
          <span><strong>{{ totalAnnonces !== null ? (totalAnnonces | number) : '—' }}</strong> annonces analysées</span>
          <button type="button" class="strip-lien" (click)="ouvrir('alertes')" title="Voir les nouvelles annonces"><strong>{{ nouveautes24h ?? '—' }}</strong> {{ nouveautes24h === 1 ? 'nouvelle' : 'nouvelles' }} en 24 h →</button>
          <span><span class="dot" [class.ok]="collecteRecente" [class.warn]="!collecteRecente"></span>
            {{ collecteRecente ? 'À jour' : 'Collecte ancienne' }} · Dernière collecte : <strong>{{ derniereCollecte || 'aucune' }}</strong></span>
          <span *ngIf="prochaineCollecte">Prochaine : <strong>{{ prochaineCollecte }}</strong></span>
        </div>

        <!-- Chaque onglet est chargé à la demande (Chart.js, Leaflet hors du bundle initial) -->
        @switch (currentTab) {
          @case ('carte') { @defer { <app-map></app-map> } @loading { <div class="loading"><div class="spinner"></div></div> } }
          @case ('stats') { @defer { <app-stats></app-stats> } @loading { <div class="loading"><div class="spinner"></div></div> } }
          @case ('estimation') { @defer { <app-estimation></app-estimation> } @loading { <div class="loading"><div class="spinner"></div></div> } }
          @case ('alertes') { @defer { <app-alerts></app-alerts> } @loading { <div class="loading"><div class="spinner"></div></div> } }
        }
      </main>

      <!-- Assistant : chargé quand le navigateur est inactif, présent sur tous les onglets -->
      @defer (on idle) { <app-chat-widget></app-chat-widget> }
    </div>
  `,
  styles: []
})
export class AppComponent implements OnInit {
  readonly tabs = [
    { id: 'carte', icon: 'map', label: 'Carte' },
    { id: 'stats', icon: 'chart', label: 'Statistiques' },
    { id: 'estimation', icon: 'calculator', label: 'Estimation' },
    { id: 'alertes', icon: 'bell', label: 'Alertes' },
  ];
  currentTab = 'carte';
  totalAnnonces: number | null = null;
  nouveautes24h: number | null = null;
  derniereCollecte: string | null = null;
  prochaineCollecte: string | null = null;
  collecteRecente = false;

  constructor(private readonly http: HttpClient) {}

  /** Onglet courant dans l'URL (#stats…) : rechargement, favoris et bouton Précédent conservent la section. */
  ouvrir(id: string): void {
    if (this.currentTab === id) return;
    this.currentTab = id;
    history.pushState(null, '', '#' + id);
    window.scrollTo({ top: 0 });
  }

  /** Lien d'évitement : un bouton plutôt qu'une ancre, le hash de l'URL portant l'onglet courant. */
  allerAuContenu(): void {
    document.getElementById('contenu')?.focus();
  }

  @HostListener('window:popstate')
  @HostListener('window:hashchange')
  lireHash(): void {
    const id = location.hash.slice(1);
    this.currentTab = this.tabs.some(t => t.id === id) ? id : 'carte';
  }

  ngOnInit(): void {
    this.lireHash();
    this.http.get<any>(API_BASE + '/api/stats').subscribe({
      next: s => this.totalAnnonces = s?.total_annonces ?? null,
      error: () => this.totalAnnonces = null,
    });
    this.http.get<any>(API_BASE + '/api/alertes/resume', { params: { jours: 1 } }).subscribe({
      next: r => this.nouveautes24h = Object.values(r?.collections || {})
        .reduce((n: number, c: any) => n + (c?.nouvelles ?? 0), 0),
      error: () => this.nouveautes24h = null,
    });
    this.http.get<any>(API_BASE + '/api/alertes/scheduler').subscribe({
      next: r => this.majCollecte(r?.jobs || []),
      error: () => {},
    });
  }

  badge(n: number): string {
    return n > 99 ? '99+' : String(n);
  }

  private majCollecte(jobs: any[]): void {
    const toDate = (v: string) => new Date(/(?:[zZ]|[+-]\d\d:\d\d)$/.test(v) ? v : v + 'Z');
    const fmt = new Intl.DateTimeFormat('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

    const dernieres = jobs.map(j => j.derniere_execution?.debut).filter(Boolean).map(toDate)
      .sort((a: Date, b: Date) => b.getTime() - a.getTime());
    if (dernieres.length) {
      this.derniereCollecte = fmt.format(dernieres[0]);
      this.collecteRecente = Date.now() - dernieres[0].getTime() < 26 * 3600 * 1000;
    }
    const prochaine = jobs.filter(j => j.prochaine_execution)
      .map(j => ({ label: j.label, date: toDate(j.prochaine_execution) }))
      .sort((a, b) => a.date.getTime() - b.date.getTime())[0];
    if (prochaine) this.prochaineCollecte = `${prochaine.label} · ${fmt.format(prochaine.date)}`;
  }
}
