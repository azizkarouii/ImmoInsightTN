import { Component, OnInit, AfterViewInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import L from 'leaflet';
import 'leaflet.heat';

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
          <div class="summary-pill"><strong>{{ totalCount }}</strong> annonces</div>
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
          {{ totalCount }} annonces
        </span>
      </div>
      <div id="map"></div>
      <div class="map-legend" *ngIf="mode === 'heat'">
        <span>Prix/m² bas</span>
        <span class="gradient-bar"></span>
        <span>Prix/m² élevé</span>
      </div>
    </div>
  `,
  styles: []
})
export class MapComponent implements OnInit, AfterViewInit {
  collections = ['clean_vente', 'clean_estival'];
  selectedCollection = 'clean_vente';
  mode: 'markers' | 'heat' = 'markers';
  private readonly tunisiaCenter: L.LatLngExpression = [34.0, 9.5];
  private readonly tunisiaBounds = L.latLngBounds([
    [30.2, 7.0],
    [37.5, 12.0],
  ]);
  private map: L.Map | null = null;
  markers: L.CircleMarker[] = [];
  heatLayer: any = null;
  totalCount = 0;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    this.map = L.map('map', {
      center: this.tunisiaCenter,
      zoom: 7,
      zoomControl: true,
      minZoom: 6,
      maxZoom: 18,
      maxBounds: this.tunisiaBounds,
      maxBoundsViscosity: 1.0,
    });
    this.map.setView(this.tunisiaCenter, 7);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(this.map);

    setTimeout(() => {
      this.map?.invalidateSize();
      this.map?.setView(this.tunisiaCenter, 7);
    }, 0);

    this.loadMarkers(this.selectedCollection);
  }

  ngOnDestroy(): void {
    this.markers.forEach(m => this.map?.removeLayer(m));
    if (this.heatLayer) {
      this.map?.removeLayer(this.heatLayer);
    }
    this.map?.remove();
    this.map = null;
  }

  setMode(mode: 'markers' | 'heat'): void {
    this.mode = mode;
    this.redraw();
  }

  private redraw(): void {
    this.markers.forEach(m => this.map?.removeLayer(m));
    this.markers = [];
    if (this.heatLayer) {
      this.map?.removeLayer(this.heatLayer);
      this.heatLayer = null;
    }

    const limit = 400;
    this.http.get<{total: number, data: any[]}>(`http://localhost:8000/api/annonces/carte?collection=${this.selectedCollection}&limit=${limit}`)
      .subscribe({
        next: (res) => {
          this.totalCount = Number(res.total || 0);
          const items = (res.data || []).filter(i =>
            Number.isFinite(i.lat) && Number.isFinite(i.lon) &&
            i.lat >= 30 && i.lat <= 38 && i.lon >= 7 && i.lon <= 12
          );
          if (this.mode === 'heat') {
            this.renderHeat(items);
          } else {
            this.renderMarkers(items);
          }
        },
        error: () => {
          if (this.map) {
            this.map.setView(this.tunisiaCenter, 7);
          }
        }
      });
  }

  private renderMarkers(items: any[]): void {
    const colorMap: Record<string, string> = {
      appartement: '#1a237e',
      villa: '#2e7d32',
      terrain: '#e65100',
      local_commercial: '#6a1b9a',
      bureau: '#00838f',
    };

    const visibleItems = items;
    const bounds = L.latLngBounds([]);
    this.markers = [];

    // build proximity groups (3 decimals ~ 100m) to detect nearby markers
    const coordMap: Record<string, number> = {};
    visibleItems.forEach(it => {
      const key = `${it.lat.toFixed(3)},${it.lon.toFixed(3)}`;
      coordMap[key] = (coordMap[key] || 0) + 1;
    });

    const seenIndex: Record<string, number> = {};

    visibleItems.forEach(item => {
      const key = `${item.lat.toFixed(3)},${item.lon.toFixed(3)}`;
      const dupCount = coordMap[key] || 1;
      const idx = (seenIndex[key] || 0);
      seenIndex[key] = idx + 1;

      // jitter nearby markers so they become individually visible at low zoom
      let lat = item.lat;
      let lon = item.lon;
      if (dupCount > 1) {
        const angle = (idx / dupCount) * Math.PI * 2;
        const radius = 0.015; // ~1.5km - visible spread at country zoom level
        lat = item.lat + Math.sin(angle) * radius;
        lon = item.lon + Math.cos(angle) * radius;
      }
      const color = colorMap[item.type_bien?.toLowerCase()] || '#9e9e9e';
      const marker = L.circleMarker([lat, lon], {
        radius: 6,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        fillOpacity: 0.8,
      }).addTo(this.map!);

      const prix = item.prix ? Number(item.prix).toLocaleString() + ' TND' : 'N/A';
      const surface = item.surface ? item.surface + ' m²' : 'N/A';

      marker.bindPopup(`
        <div style="min-width:180px">
          <b style="color:#1a237e;font-size:1rem">${(item.titre || 'Sans titre').slice(0, 50)}</b><br/>
          <hr style="margin:6px 0;border:none;border-top:1px solid #e0e0e0"/>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:0.85rem">
            <span>💰 ${prix}</span>
            <span>📐 ${surface}</span>
            <span>🏷️ ${item.type_bien || 'N/A'}</span>
            <span>📍 ${item.gouvernorat || item.ville || 'N/A'}</span>
          </div>
          <hr style="margin:6px 0;border:none;border-top:1px solid #e0e0e0"/>
          <a href="${item.url || '#'}" target="_blank" style="color:#00bcd4;font-size:0.8rem">Voir l'annonce →</a>
        </div>
      `);

      this.markers.push(marker);
      bounds.extend([lat, lon]);
    });

    if (bounds.isValid() && this.map) {
      this.map.fitBounds(bounds.pad(0.25), { maxZoom: 9 });
    } else if (this.map) {
      this.map.setView(this.tunisiaCenter, 7);
    }
  }

  private renderHeat(items: any[]): void {
    const visibleItems = items;
    if (!visibleItems.length) return;

    const source = visibleItems.filter(i => i.prix && i.surface && i.surface > 0);
    const points: [number, number, number][] = source.length
      ? source.map(i => [i.lat, i.lon, Math.min(1, (Number(i.prix) / Number(i.surface)) / 2000)])
      : visibleItems.map(i => [i.lat, i.lon, 0.3]);

    this.heatLayer = (L as any).heatLayer(points, {
      radius: 22,
      blur: 18,
      maxZoom: 15,
      minOpacity: 0.25,
      gradient: {
        0.0: '#2196f3',
        0.4: '#00bcd4',
        0.6: '#ff9800',
        0.8: '#e65100',
        1.0: '#c62828',
      },
    }).addTo(this.map!);

    const bounds = L.latLngBounds(visibleItems.map(item => [item.lat, item.lon] as [number, number]));
    if (bounds.isValid() && this.map) {
      this.map.fitBounds(bounds.pad(0.25), { maxZoom: 9 });
    } else if (this.map) {
      this.map.setView(this.tunisiaCenter, 7);
    }
  }

  loadMarkers(collection: string): void {
    this.selectedCollection = collection;
    this.redraw();
  }

  collectionLabel(collection: string): string {
    return collection === 'clean_vente' ? 'Vente' : 'Estival';
  }
}
