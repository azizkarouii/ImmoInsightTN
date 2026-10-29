import { Component, AfterViewInit, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import L from 'leaflet';
import 'leaflet.heat';
import 'leaflet.markercluster';

// Types de résultat de géocodage assez précis pour situer un bien ; pour les autres
// (ville, quartier, délégation...) la position affichée est le centre de la zone.
const PRECISE_GEO_TYPES = new Set(['house', 'building', 'apartments', 'residential', 'street', 'road', 'address']);

@Component({
  selector: 'app-map',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card map-wrapper">
      <div class="section-head" style="padding:18px 16px 0 16px;margin-bottom:0;align-items:center">
        <div>
          <p class="eyebrow">Lecture géographique</p>
          <h2 style="margin:0">Carte des annonces et intensité des prix</h2>
          <p class="section-copy">Vue carte, heatmap et repérage rapide des biens avec qualité et fiabilité visibles.</p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ totalCount }}</strong> annonces géolocalisées</div>
          <div class="summary-pill"><strong>{{ visibleCount }}</strong> dans la vue</div>
          <div class="summary-pill"><strong>{{ mode === 'heat' ? 'Heatmap' : 'Marqueurs' }}</strong> actif</div>
        </div>
      </div>

      <div class="map-toolbar">
        <button *ngFor="let col of collections"
                [class.active]="selectedCollection === col"
                (click)="loadMarkers(col)">
          {{ collectionLabel(col) }}
        </button>
        <span style="flex:1"></span>
        <button class="mode-btn"
                [class.active]="mode === 'heat'"
                (click)="setMode('heat')">🔥 Heatmap prix</button>
        <button class="mode-btn"
                [class.active]="mode === 'markers'"
                (click)="setMode('markers')">📍 Marqueurs</button>
        <span style="font-size:0.8rem;color:var(--text-light)">
          {{ loading ? 'Chargement…' : error ? error : visibleCount + ' dans la vue' }}
        </span>
      </div>
      <div class="map-stage">
        <div id="map"></div>
        <div class="map-legend" *ngIf="mode === 'heat'">
          <span>{{ heatLabel }} bas</span>
          <span class="gradient-bar"></span>
          <span>{{ heatLabel }} élevé</span>
        </div>
      </div>
    </div>
  `,
  styles: []
})
export class MapComponent implements AfterViewInit, OnDestroy {
  collections = ['clean_vente', 'clean_estival'];
  selectedCollection = 'clean_vente';
  mode: 'markers' | 'heat' = 'markers';
  loading = false;
  error: string | null = null;
  totalCount = 0;
  visibleCount = 0;

  private readonly tunisiaCenter: L.LatLngExpression = [34.0, 9.5];
  private readonly tunisiaBounds = L.latLngBounds([
    [29.5, 6.5],
    [38.0, 12.5],
  ]);
  private map: L.Map | null = null;
  private clusterLayer: L.MarkerClusterGroup | null = null;
  private heatLayer: L.Layer | null = null;
  private items: any[] = [];
  private request: Subscription | null = null;

  constructor(private http: HttpClient) {}

  get heatLabel(): string {
    return this.selectedCollection === 'clean_estival' ? 'Prix/nuit' : 'Prix/m²';
  }

  ngAfterViewInit(): void {
    this.map = L.map('map', {
      center: this.tunisiaCenter,
      zoom: 7,
      // Zoom fractionnaire : sinon fitBounds sur toute la Tunisie retombe au
      // zoom 6 et affiche l'Algérie et la Libye
      zoomSnap: 0.25,
      zoomControl: true,
      minZoom: 6,
      maxZoom: 18,
      maxBounds: this.tunisiaBounds,
      maxBoundsViscosity: 1.0,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(this.map);

    this.map.on('moveend', () => this.updateVisibleCount());

    // Hors du cycle ngAfterViewInit : modifier loading/visibleCount ici
    // déclenche NG0100 (ExpressionChangedAfterItHasBeenChecked). Le conteneur
    // est aussi dimensionné par le CSS après le premier rendu.
    setTimeout(() => {
      this.map?.invalidateSize();
      this.loadMarkers(this.selectedCollection);
    }, 0);
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
    this.map?.remove();
    this.map = null;
  }

  loadMarkers(collection: string): void {
    this.selectedCollection = collection;
    this.fetchItems();
  }

  setMode(mode: 'markers' | 'heat'): void {
    if (this.mode === mode) return;
    this.mode = mode;
    // Les données sont déjà chargées : un changement de mode ne refait pas d'appel API
    this.render(false);
  }

  collectionLabel(collection: string): string {
    return collection === 'clean_vente' ? 'Vente' : 'Estival';
  }

  private fetchItems(): void {
    // Annule la requête précédente : sinon un clic rapide Vente → Estival peut
    // afficher les deux jeux de données superposés
    this.request?.unsubscribe();
    this.loading = true;
    this.error = null;

    this.request = this.http
      .get<{ total: number, data: any[] }>('http://localhost:8000/api/annonces/carte', {
        params: { collection: this.selectedCollection, limit: 1000 },
      })
      .subscribe({
        next: (res) => {
          this.items = (res.data || [])
            .map(i => ({ ...i, lat: Number(i.lat), lon: Number(i.lon) }))
            .filter(i => Number.isFinite(i.lat) && Number.isFinite(i.lon));
          this.totalCount = this.items.length;
          this.loading = false;
          this.render(true);
        },
        error: () => {
          this.items = [];
          this.totalCount = 0;
          this.loading = false;
          this.error = 'API indisponible';
          this.render(true);
        },
      });
  }

  private clearLayers(): void {
    if (this.clusterLayer) {
      this.map?.removeLayer(this.clusterLayer);
      this.clusterLayer = null;
    }
    if (this.heatLayer) {
      this.map?.removeLayer(this.heatLayer);
      this.heatLayer = null;
    }
  }

  private render(fit: boolean): void {
    if (!this.map) return;
    this.clearLayers();

    if (this.mode === 'heat') {
      this.renderHeat();
    } else {
      this.renderMarkers();
    }

    if (fit) {
      const bounds = L.latLngBounds(this.items.map(i => [i.lat, i.lon] as [number, number]));
      if (bounds.isValid()) {
        this.map.fitBounds(bounds.pad(0.05), { maxZoom: 12 });
      } else {
        this.map.setView(this.tunisiaCenter, 7);
      }
    }
    this.updateVisibleCount();
  }

  private renderMarkers(): void {
    const colorMap: Record<string, string> = {
      appartement: '#1a237e',
      villa: '#2e7d32',
      terrain: '#e65100',
      local_commercial: '#6a1b9a',
      bureau: '#00838f',
    };

    // Plusieurs annonces partagent souvent la même position (géocodage au niveau
    // ville/quartier) : le clustering les regroupe et les déploie au zoom max
    // au lieu de les décaler artificiellement.
    this.clusterLayer = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      maxClusterRadius: 40,
    });

    for (const item of this.items) {
      const color = colorMap[String(item.type_bien || '').toLowerCase()] || '#9e9e9e';
      const marker = L.circleMarker([item.lat, item.lon], {
        radius: 7,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        fillOpacity: 0.85,
      });
      marker.bindPopup(this.popupHtml(item));
      // circleMarker n'est pas un L.Marker mais markercluster l'accepte (il a getLatLng)
      this.clusterLayer.addLayer(marker as unknown as L.Marker);
    }

    this.clusterLayer.addTo(this.map!);
  }

  private renderHeat(): void {
    if (!this.items.length) return;

    // Vente : prix/m² ; estival : prix/nuit (pas de surface)
    const value = (i: any): number | null => {
      const prix = Number(i.prix);
      if (!Number.isFinite(prix) || prix <= 0) return null;
      if (this.selectedCollection === 'clean_estival') return prix;
      const surface = Number(i.surface);
      return Number.isFinite(surface) && surface > 0 ? prix / surface : null;
    };

    // Normalisation par percentiles du jeu courant : l'ancien diviseur fixe
    // (prix/m² / 2000) saturait presque tous les points au rouge.
    const values = this.items.map(value).filter((v): v is number => v !== null).sort((a, b) => a - b);
    const lo = values.length ? values[Math.floor(values.length * 0.05)] : 0;
    const hi = values.length ? values[Math.floor((values.length - 1) * 0.95)] : 1;
    const span = hi > lo ? hi - lo : 1;

    const points: [number, number, number][] = this.items.map(i => {
      const v = value(i);
      const intensity = v === null ? 0.3 : Math.min(1, Math.max(0.05, (v - lo) / span));
      return [i.lat, i.lon, intensity];
    });

    this.heatLayer = (L as any).heatLayer(points, {
      radius: 25,
      blur: 18,
      maxZoom: 12,
      max: 1,
      minOpacity: 0.3,
      gradient: {
        0.0: '#2196f3',
        0.4: '#00bcd4',
        0.6: '#ff9800',
        0.8: '#e65100',
        1.0: '#c62828',
      },
    }).addTo(this.map!);
  }

  private updateVisibleCount(): void {
    if (!this.map) {
      this.visibleCount = 0;
      return;
    }
    const bounds = this.map.getBounds();
    this.visibleCount = this.items.filter(i => bounds.contains([i.lat, i.lon])).length;
  }

  private popupHtml(item: any): string {
    const esc = (value: unknown): string =>
      String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

    const prixUnit = this.selectedCollection === 'clean_estival' ? ' TND/nuit' : ' TND';
    const prix = item.prix ? Number(item.prix).toLocaleString('fr-FR') + prixUnit : 'N/A';
    const surface = item.surface ? item.surface + ' m²' : 'N/A';
    const lieu = [item.ville, item.gouvernorat]
      .filter((v, idx, arr) => v && arr.indexOf(v) === idx)
      .join(', ') || 'N/A';
    const url = /^https?:\/\//i.test(item.url || '') ? item.url : null;
    const approx = item.geo_type && !PRECISE_GEO_TYPES.has(item.geo_type)
      ? `<div style="margin-top:6px;font-size:0.75rem;color:#8a6d3b">≈ Position approximative (${esc(item.geocoded_query || lieu)})</div>`
      : '';

    return `
      <div style="min-width:180px">
        <b style="color:#1a237e;font-size:1rem">${esc((item.titre || 'Sans titre').slice(0, 60))}</b><br/>
        <hr style="margin:6px 0;border:none;border-top:1px solid #e0e0e0"/>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:0.85rem">
          <span>💰 ${esc(prix)}</span>
          <span>📐 ${esc(surface)}</span>
          <span>🏷️ ${esc(item.type_bien || 'N/A')}</span>
          <span>📍 ${esc(lieu)}</span>
        </div>
        ${approx}
        <hr style="margin:6px 0;border:none;border-top:1px solid #e0e0e0"/>
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener" style="color:#00bcd4;font-size:0.8rem">Voir l'annonce →</a>` : ''}
      </div>
    `;
  }
}
