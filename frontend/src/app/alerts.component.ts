import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="card">
      <div class="section-head">
        <div>
          <p class="eyebrow">Veille active</p>
          <h2>Alertes et notifications</h2>
          <p class="section-copy">Suivez les nouvelles annonces, les variations de prix et les scores de fiabilité les plus faibles.</p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ data.length }}</strong> résultats</div>
          <div class="summary-pill"><strong>{{ activeTab }}</strong> vue active</div>
        </div>
      </div>

      <div class="alert-tabs">
        <button [class.active]="activeTab === 'nouvelles'" (click)="loadNouvelles()">
          🆕 Nouvelles annonces
        </button>
        <button [class.active]="activeTab === 'prix'" (click)="loadPrix()">
          💰 Prix changés
        </button>
        <button [class.active]="activeTab === 'fiabilite'" (click)="loadFiabilite()">
          ⚠️ Fiabilité faible
        </button>
      </div>

      <div *ngIf="loading" class="loading">
        <div class="spinner"></div>
        Chargement...
      </div>

      <div *ngIf="!loading && data.length > 0">
        <p style="color:var(--text-secondary);margin-bottom:12px">
          {{ data.length }} résultat(s)
        </p>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th *ngFor="let col of columns">{{ formatHeader(col) }}</th>
            </tr></thead>
            <tbody>
              <tr *ngFor="let row of data">
                <td *ngFor="let col of columns">
                  <ng-container [ngSwitch]="col">
                    <span *ngSwitchCase="'source'" class="badge badge-info">{{ row[col] }}</span>
                    <span *ngSwitchCase="'fiabilite'" [class.badge-success]="row[col] > 60"
                          [class.badge-warning]="row[col] <= 60 && row[col] > 30"
                          [class.badge-danger]="row[col] <= 30">
                      {{ row[col] }}/100
                    </span>
                    <span *ngSwitchCase="'prix'">{{ row[col] | number:'1.0-0' }} TND</span>
                      <span *ngSwitchCase="'scraped_at'">{{ formatDate(row[col]) }}</span>
                      <span *ngSwitchDefault>{{ renderCell(row[col]) }}</span>
                  </ng-container>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div *ngIf="!loading && data.length === 0" class="loading" style="color:var(--text-light)">
        Aucun résultat pour cette catégorie.
      </div>
    </div>
  `,
  styles: []
})
export class AlertsComponent implements OnInit {
  loading = false;
  data: any[] = [];
  columns: string[] = [];
  activeTab = 'nouvelles';

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadNouvelles();
  }

  formatHeader(col: string): string {
    const map: Record<string, string> = {
      titre: 'Titre',
      url: 'URL',
      prix: 'Prix',
      source: 'Source',
      type_bien: 'Type',
      gouvernorat: 'Gouvernorat',
      fiabilite: 'Fiabilité',
      scraped_at: 'Scrapé le',
      is_new: 'Nouveau',
      nb_pieces: 'Pièces',
      nb_chambres: 'Chambres',
    };
    return map[col] || col;
  }

  formatDate(val: any): string {
    if (!val) return '—';
    const date = new Date(val);
    if (Number.isNaN(date.getTime())) return String(val).slice(0, 19);
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date);
  }

  renderCell(val: any): string {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'boolean') return val ? 'Oui' : 'Non';
    if (typeof val === 'object') return JSON.stringify(val).slice(0, 60);
    return String(val).slice(0, 80);
  }

  loadNouvelles(): void {
    this.activeTab = 'nouvelles';
    this.fetch('http://localhost:8000/api/alertes/nouvelles');
  }

  loadPrix(): void {
    this.activeTab = 'prix';
    this.fetch('http://localhost:8000/api/alertes/prix');
  }

  loadFiabilite(): void {
    this.activeTab = 'fiabilite';
    this.fetch('http://localhost:8000/api/fiabilite/alertes');
  }

  private fetch(url: string): void {
    this.loading = true;
    this.http.get<any>(url).subscribe({
      next: res => {
        const items = res?.data || [];
        this.data = Array.isArray(items) ? items.slice(0, 50) : [];
        this.columns = this.data.length > 0 ? Object.keys(this.data[0]) : [];
        this.loading = false;
      },
      error: () => this.loading = false
    });
  }
}