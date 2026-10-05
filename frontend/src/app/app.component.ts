import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MapComponent } from './map.component';
import { EstimationComponent } from './estimation.component';
import { StatsComponent } from './stats.component';
import { AlertsComponent } from './alerts.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, MapComponent, EstimationComponent, StatsComponent, AlertsComponent],
  template: `
    <div class="app-shell">
      <header class="app-header">
        <div class="logo">
          <div class="icon">🏠</div>
          <div>
            ImmoInsight TN
            <span class="subtitle">Marché immobilier, données nettoyées et lecture premium</span>
          </div>
        </div>
        <nav class="nav-tabs">
          <button [class.active]="currentTab === 'carte'" (click)="currentTab = 'carte'">
            🗺️ Carte
          </button>
          <button [class.active]="currentTab === 'stats'" (click)="currentTab = 'stats'">
            📊 Statistiques
          </button>
          <button [class.active]="currentTab === 'estimation'" (click)="currentTab = 'estimation'">
            📐 Estimation
          </button>
          <button [class.active]="currentTab === 'alertes'" (click)="currentTab = 'alertes'">
            🔔 Alertes
          </button>
        </nav>
      </header>

      <section class="hero-panel">
        <div>
          <p class="eyebrow">Pilotage marché</p>
          <h1>Des annonces plus propres, des signaux plus lisibles, et une décision plus rapide.</h1>
          <p class="hero-copy">
            Le pipeline enrichit les annonces avec la géolocalisation, une qualité de données visible et
            des métriques marché mieux hiérarchisées.
          </p>
        </div>
        <div class="hero-pills">
          <div class="hero-pill"><strong>Nettoyage</strong> prix et surfaces</div>
          <div class="hero-pill"><strong>Qualité</strong> score exploitable</div>
          <div class="hero-pill"><strong>Carte</strong> + heatmap</div>
          <div class="hero-pill"><strong>ROI</strong> estimation et alertes</div>
        </div>
      </section>

      <main class="main-content">
        <app-stats *ngIf="currentTab === 'stats'"></app-stats>
        <app-map *ngIf="currentTab === 'carte'"></app-map>
        <app-estimation *ngIf="currentTab === 'estimation'"></app-estimation>
        <app-alerts *ngIf="currentTab === 'alertes'"></app-alerts>
      </main>
    </div>
  `,
  styles: []
})
export class AppComponent {
  currentTab = 'carte';
}