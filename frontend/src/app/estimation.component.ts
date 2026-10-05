import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-estimation',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  template: `
    <div class="card estimation-shell" style="margin-bottom:20px">
      <div class="section-head">
        <div>
          <p class="eyebrow">Calcul intelligent</p>
          <h2>Estimation de prix et lecture de rentabilité</h2>
          <p class="section-copy">
            Combine l'AVM vente, le loyer de marché, le calcul ROI et des repères de zones pour sortir d'un simple formulaire.
          </p>
        </div>
        <div class="summary-pills">
          <div class="summary-pill"><strong>{{ topZones.length }}</strong> zones analysées</div>
          <div class="summary-pill"><strong>3</strong> scénarios d'estimation</div>
        </div>
      </div>

      <div class="insight-strip">
        <div class="insight-card">
          <span>Lecture marché</span>
          <strong>Zone, prix, loyer, ROI</strong>
        </div>
        <div class="insight-card">
          <span>Nettoyage data</span>
          <strong>Libellés aberrants filtrés</strong>
        </div>
        <div class="insight-card">
          <span>Sortie</span>
          <strong>Résultats comparables et lisibles</strong>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-tile">
          <span>AVM vente</span>
          <strong>XGBoost + LightGBM</strong>
        </div>
        <div class="summary-tile">
          <span>Loyer classique</span>
          <strong>Prix/m² local</strong>
        </div>
        <div class="summary-tile">
          <span>ROI</span>
          <strong>Score /100</strong>
        </div>
        <div class="summary-tile">
          <span>Estival</span>
          <strong>Prix / nuit</strong>
        </div>
      </div>

      <form [formGroup]="estimationForm" (ngSubmit)="onSubmit()">
        <div class="form-grid">
          <div class="form-group">
            <label>Surface (m²) *</label>
            <input type="number" formControlName="surface" placeholder="ex: 120" />
          </div>
          <div class="form-group">
            <label>Type de bien</label>
            <select formControlName="type_bien">
              <option value="">— Sélectionner —</option>
              <option value="appartement">Appartement</option>
              <option value="villa">Villa / Maison</option>
              <option value="terrain">Terrain</option>
            </select>
          </div>
          <div class="form-group">
            <label>Nombre de pièces</label>
            <input type="number" formControlName="nb_pieces" placeholder="ex: 3" />
          </div>
          <div class="form-group">
            <label>Nombre de chambres</label>
            <input type="number" formControlName="nb_chambres" placeholder="ex: 2" />
          </div>
          <div class="form-group">
            <label>Gouvernorat</label>
            <input type="text" formControlName="gouvernorat" placeholder="ex: Tunis" />
          </div>
          <div class="form-group">
            <label>Parking</label>
            <select formControlName="has_parking">
              <option value="0">Non</option>
              <option value="1">Oui</option>
            </select>
          </div>
          <div class="form-group">
            <label>Ascenseur</label>
            <select formControlName="has_ascenseur">
              <option value="0">Non</option>
              <option value="1">Oui</option>
            </select>
          </div>
          <div class="form-group">
            <label>Piscine</label>
            <select formControlName="has_piscine">
              <option value="0">Non</option>
              <option value="1">Oui</option>
            </select>
          </div>
        </div>

        <button type="submit" class="btn btn-accent" [disabled]="estimationForm.invalid || loading">
          <span *ngIf="loading" class="spinner" style="display:inline-block;width:16px;height:16px;border-width:2px;margin-right:6px;vertical-align:middle"></span>
          {{ loading ? 'Calcul en cours...' : 'Estimer le prix' }}
        </button>
      </form>

      <div *ngIf="result" class="result-box">
        <h3>Résultat de l'estimation</h3>
        <div class="result-price">
          {{ result.prix_estime | number:'1.0-0' }} TND
        </div>
        <div class="result-range">
          Intervalle de confiance (90 %) :
          <strong>{{ result.intervalle_bas | number:'1.0-0' }}</strong> —
          <strong>{{ result.intervalle_haut | number:'1.0-0' }}</strong> TND
        </div>
        <div class="summary-grid" style="margin-top:16px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
          <div class="summary-tile">
            <span>XGBoost</span>
            <strong>{{ result.prix_xgb | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>LightGBM</span>
            <strong>{{ result.prix_lgb | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>Intervalle bas</span>
            <strong>{{ result.intervalle_bas | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>Intervalle haut</span>
            <strong>{{ result.intervalle_haut | number:'1.0-0' }}</strong>
          </div>
        </div>
      </div>

      <div *ngIf="error" class="result-box" style="background:#fbe9e7">
        <p style="color:#c62828">⚠️ {{ error }}</p>
      </div>
    </div>

    <div class="card estimation-card" style="margin-top:20px">
      <h2>🏠 Estimation de loyer mensuel (M2)</h2>
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:0.9rem">
        Référence marché par zone et type de bien.
      </p>
      <div class="form-grid">
        <div class="form-group">
          <label>Surface (m²)</label>
          <input type="number" [(ngModel)]="loyerForm.surface" placeholder="ex: 90" />
        </div>
        <div class="form-group">
          <label>Ville</label>
          <input type="text" [(ngModel)]="loyerForm.ville" placeholder="ex: La Marsa, Tunis..." />
        </div>
        <div class="form-group">
          <label>Type de bien</label>
          <select [(ngModel)]="loyerForm.type_bien">
            <option value="appartement">Appartement</option>
            <option value="villa">Villa / Maison</option>
          </select>
        </div>
        <div class="form-group">
          <label>Nombre de pièces</label>
          <input type="number" [(ngModel)]="loyerForm.nb_pieces" placeholder="ex: 3" />
        </div>
      </div>
      <button class="btn btn-accent" (click)="estimateLoyer()" [disabled]="loyerLoading">
        <span *ngIf="loyerLoading" class="spinner" style="display:inline-block;width:16px;height:16px;border-width:2px;margin-right:6px;vertical-align:middle"></span>
        Estimer le loyer
      </button>

      <div *ngIf="loyerResult" class="result-box">
        <h3>Loyer estimé</h3>
        <div class="result-price">
          {{ loyerResult.loyer_estime | number:'1.0-0' }} TND / mois
        </div>
        <div class="result-range">
          Intervalle (±15 %) :
          <strong>{{ loyerResult.intervalle_bas | number:'1.0-0' }}</strong> —
          <strong>{{ loyerResult.intervalle_haut | number:'1.0-0' }}</strong> TND
        </div>
        <div style="margin-top:12px;font-size:0.8rem;color:var(--text-light)">
          Référence : {{ loyerResult.prix_m2_reference }} DT/m²/mois · {{ loyerResult.modele }}
        </div>
      </div>
      <div *ngIf="loyerError" class="result-box" style="background:#fbe9e7">
        <p style="color:#c62828">⚠️ {{ loyerError }}</p>
      </div>
    </div>

    <div class="card estimation-card" style="margin-top:20px">
      <h2>🌊 Estimation estivale</h2>
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:0.9rem">
        Prix de nuit projeté à partir de la zone, du score avis et de l'accès plage.
      </p>
      <div class="form-grid">
        <div class="form-group">
          <label>Ville *</label>
          <input type="text" [(ngModel)]="estivalForm.ville" placeholder="ex: Hammamet" />
        </div>
        <div class="form-group">
          <label>Score avis</label>
          <input type="number" [(ngModel)]="estivalForm.score_avis" placeholder="ex: 4.5" step="0.1" />
        </div>
        <div class="form-group">
          <label>Distance plage (km)</label>
          <input type="number" [(ngModel)]="estivalForm.dist_plages" placeholder="ex: 0.6" step="0.1" />
        </div>
      </div>
      <button class="btn btn-accent" (click)="estimateEstival()" [disabled]="estivalLoading || !estivalForm.ville">
        <span *ngIf="estivalLoading" class="spinner" style="display:inline-block;width:16px;height:16px;border-width:2px;margin-right:6px;vertical-align:middle"></span>
        Estimer le prix / nuit
      </button>

      <div *ngIf="estivalResult" class="result-box">
        <h3>Prix estival estimé</h3>
        <div class="result-price">
          {{ estivalResult.prix_nuit_estime | number:'1.0-0' }} TND / nuit
        </div>
        <div class="result-range">
          Base modèle : <strong>{{ estivalResult.modele }}</strong>
        </div>
      </div>

      <div *ngIf="estivalError" class="result-box" style="background:#fbe9e7">
        <p style="color:#c62828">⚠️ {{ estivalError }}</p>
      </div>
    </div>

    <div class="card estimation-card" style="margin-top:20px">
      <h2>💰 Calcul ROI investisseur</h2>
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:0.9rem">
        Rendement combiné avec lecture de risque et temps de retour.
      </p>
      <div class="form-grid">
        <div class="form-group">
          <label>Prix d'achat (TND) *</label>
          <input type="number" [(ngModel)]="roiForm.prix" placeholder="ex: 300000" />
        </div>
        <div class="form-group">
          <label>Loyer mensuel classique (TND)</label>
          <input type="number" [(ngModel)]="roiForm.loyer_mensuel" placeholder="ex: 1500" />
        </div>
        <div class="form-group">
          <label>Prix / nuit estival (TND)</label>
          <input type="number" [(ngModel)]="roiForm.prix_nuit" placeholder="ex: 350" />
        </div>
        <div class="form-group">
          <label>Nuits louées / an</label>
          <input type="number" [(ngModel)]="roiForm.nuits_an" value="90" />
        </div>
      </div>
      <button class="btn btn-accent" (click)="calculateRoi()" [disabled]="roiLoading">
        <span *ngIf="roiLoading" class="spinner" style="display:inline-block;width:16px;height:16px;border-width:2px;margin-right:6px;vertical-align:middle"></span>
        Calculer le ROI
      </button>

      <div *ngIf="roiResult" class="result-box">
        <h3>Résultat ROI</h3>
        <div class="result-price">
          Rendement net : {{ roiResult.rendement_net_pct }} %
          <span class="badge" [ngClass]="{
            'badge-success': roiResult.label_roi === 'excellent' || roiResult.label_roi === 'bon',
            'badge-warning': roiResult.label_roi === 'moyen' || roiResult.label_roi === 'faible',
            'badge-danger': roiResult.label_roi === 'deficitaire'
          }" style="margin-left:8px">{{ roiResult.label_roi }}</span>
        </div>
        <div class="result-range">
          Score ROI : <strong>{{ roiResult.score_roi }}/100</strong> ·
          Temps de retour : <strong>{{ roiResult.temps_retour_annees ? roiResult.temps_retour_annees + ' ans' : '—' }}</strong>
        </div>
        <div class="summary-grid" style="margin-top:16px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
          <div class="summary-tile">
            <span>Coût total</span>
            <strong>{{ roiResult.cout_total_acquisition | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>Revenu annuel</span>
            <strong>{{ roiResult.revenu_annuel_total | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>Classique</span>
            <strong>{{ roiResult.revenu_annuel_classique | number:'1.0-0' }}</strong>
          </div>
          <div class="summary-tile">
            <span>Estival</span>
            <strong>{{ roiResult.revenu_annuel_estival | number:'1.0-0' }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div class="card estimation-card" style="margin-top:20px">
      <div class="section-head">
        <div>
          <p class="eyebrow">Références de marché</p>
          <h2>Meilleures zones ROI</h2>
          <p class="section-copy">Les zones avec le meilleur équilibre entre prix d’achat, loyer estimé et revenu estival.</p>
        </div>
      </div>

      <div class="table-wrap" *ngIf="topZones.length > 0; else zonesLoadingOrEmpty">
        <table>
          <thead>
            <tr>
              <th>Zone</th>
              <th>Prix moyen</th>
              <th>Loyer estimé</th>
              <th>Prix nuit</th>
              <th>Rendement net</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let zone of topZones">
              <td>
                <div class="zone-name">{{ zone.zone_label || zone.ville || zone.gouvernorat || '—' }}</div>
                <div class="zone-subtitle">{{ zone.nb_annonces }} annonces</div>
              </td>
              <td>{{ zone.prix_moyen | number:'1.0-0' }} TND</td>
              <td>{{ zone.loyer_mensuel_estime | number:'1.0-0' }} TND</td>
              <td>{{ zone.prix_nuit_estival_moyen ? (zone.prix_nuit_estival_moyen | number:'1.0-0') : '—' }}</td>
              <td>{{ zone.rendement_net_pct | number:'1.0-1' }} %</td>
              <td><span class="badge badge-info">{{ zone.score_roi }}/100</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <ng-template #zonesLoadingOrEmpty>
        <div class="loading" style="justify-content:flex-start;padding:8px 0 0">
          <span *ngIf="zonesLoading" class="spinner"></span>
          <span>{{ zonesLoading ? 'Chargement des zones...' : 'Aucune zone disponible pour le moment.' }}</span>
        </div>
      </ng-template>
    </div>
  `,
  styles: [`
    :host {
      display: block;
    }

    .estimation-shell {
      background: linear-gradient(180deg, rgba(10, 38, 64, 0.03), rgba(255, 255, 255, 0.98));
      border: 1px solid rgba(26, 35, 126, 0.08);
    }

    .estimation-card {
      border: 1px solid rgba(26, 35, 126, 0.08);
      box-shadow: 0 18px 50px rgba(15, 23, 42, 0.06);
    }

    .insight-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin: 16px 0 18px;
    }

    .insight-card {
      padding: 14px 16px;
      border-radius: 16px;
      background: linear-gradient(135deg, rgba(26, 35, 126, 0.08), rgba(0, 188, 212, 0.08));
      border: 1px solid rgba(26, 35, 126, 0.08);
    }

    .insight-card span,
    .zone-subtitle {
      display: block;
      color: var(--text-light);
      font-size: 0.78rem;
    }

    .insight-card strong {
      display: block;
      margin-top: 4px;
      color: var(--text-primary);
      font-size: 0.96rem;
    }

    .zone-name {
      font-weight: 700;
      color: var(--text-primary);
      text-transform: capitalize;
    }

    .table-wrap {
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid rgba(26, 35, 126, 0.08);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }

    thead th {
      background: rgba(26, 35, 126, 0.04);
      color: var(--text-primary);
      font-weight: 700;
    }

    tbody tr:hover {
      background: rgba(0, 188, 212, 0.04);
    }

    td, th {
      padding: 14px 16px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.18);
      text-align: left;
      white-space: nowrap;
    }

    tbody tr:last-child td {
      border-bottom: none;
    }
  `]
})
export class EstimationComponent implements OnInit {
  estimationForm: FormGroup;
  loading = false;
  result: any = null;
  error: string | null = null;

  roiForm = { prix: null as number | null, loyer_mensuel: null as number | null, prix_nuit: null as number | null, nuits_an: 90 };
  roiResult: any = null;
  roiLoading = false;

  loyerForm = { surface: null as number | null, ville: '', type_bien: 'appartement', nb_pieces: null as number | null };
  loyerResult: any = null;
  loyerError: string | null = null;
  loyerLoading = false;

  estivalForm = { ville: '', score_avis: null as number | null, dist_plages: null as number | null };
  estivalResult: any = null;
  estivalError: string | null = null;
  estivalLoading = false;

  topZones: any[] = [];
  zonesLoading = false;

  constructor(private fb: FormBuilder, private http: HttpClient) {
    this.estimationForm = this.fb.group({
      surface: ['', Validators.required],
      type_bien: [''],
      nb_pieces: [''],
      nb_chambres: [''],
      gouvernorat: [''],
      has_parking: ['0'],
      has_ascenseur: ['0'],
      has_piscine: ['0'],
    });
  }

  ngOnInit(): void {
    this.loadTopZones();
  }

  onSubmit(): void {
    if (this.estimationForm.invalid) return;
    this.loading = true;
    this.result = null;
    this.error = null;

    let params = new HttpParams();
    const formVal = this.estimationForm.value;
    Object.keys(formVal).forEach(key => {
      if (formVal[key] !== null && formVal[key] !== undefined && formVal[key] !== '') {
        params = params.set(key, formVal[key]);
      }
    });

    this.http.get<any>('http://localhost:8000/api/vente/estimation', { params })
      .subscribe({
        next: res => {
          if (res.statut === 'erreur') {
            this.error = res.message;
          } else {
            this.result = res;
          }
          this.loading = false;
        },
        error: err => {
          this.error = 'Erreur de connexion au serveur';
          this.loading = false;
        }
      });
  }

  estimateLoyer(): void {
    this.loyerLoading = true;
    this.loyerResult = null;
    this.loyerError = null;
    let params = new HttpParams();
    const f = this.loyerForm;
    if (f.surface) params = params.set('surface', f.surface);
    if (f.ville) params = params.set('ville', f.ville);
    params = params.set('type_bien', f.type_bien);
    if (f.nb_pieces) params = params.set('nb_pieces', f.nb_pieces);

    this.http.get<any>('http://localhost:8000/api/location/estimation', { params })
      .subscribe({
        next: res => {
          if (res.statut === 'erreur') {
            this.loyerError = res.message;
          } else {
            this.loyerResult = res;
          }
          this.loyerLoading = false;
        },
        error: () => {
          this.loyerError = 'Erreur de connexion au serveur';
          this.loyerLoading = false;
        }
      });
  }

  estimateEstival(): void {
    if (!this.estivalForm.ville) return;
    this.estivalLoading = true;
    this.estivalResult = null;
    this.estivalError = null;

    let params = new HttpParams().set('ville', this.estivalForm.ville);
    if (this.estivalForm.score_avis !== null && this.estivalForm.score_avis !== undefined) {
      params = params.set('score_avis', this.estivalForm.score_avis);
    }
    if (this.estivalForm.dist_plages !== null && this.estivalForm.dist_plages !== undefined) {
      params = params.set('dist_plages', this.estivalForm.dist_plages);
    }

    this.http.get<any>('http://localhost:8000/api/estival/estimation', { params })
      .subscribe({
        next: res => {
          if (res.statut === 'erreur') {
            this.estivalError = res.message;
          } else {
            this.estivalResult = res;
          }
          this.estivalLoading = false;
        },
        error: () => {
          this.estivalError = 'Erreur de connexion au serveur';
          this.estivalLoading = false;
        }
      });
  }

  calculateRoi(): void {
    if (!this.roiForm.prix) return;
    this.roiLoading = true;
    this.roiResult = null;
    let params = new HttpParams();
    params = params.set('prix', this.roiForm.prix);
    if (this.roiForm.loyer_mensuel) params = params.set('loyer_mensuel', this.roiForm.loyer_mensuel);
    if (this.roiForm.prix_nuit) params = params.set('prix_nuit', this.roiForm.prix_nuit);
    params = params.set('nuits_an', this.roiForm.nuits_an || 90);

    this.http.get<any>('http://localhost:8000/api/roi/calculer', { params })
      .subscribe({
        next: res => { this.roiResult = res; this.roiLoading = false; },
        error: () => { this.roiResult = { statut: 'erreur', message: 'Erreur de connexion' }; this.roiLoading = false; }
      });
  }

  loadTopZones(): void {
    this.zonesLoading = true;
    this.http.get<any>('http://localhost:8000/api/roi/top_zones', { params: { limit: 5 } as any })
      .subscribe({
        next: res => {
          const raw = Array.isArray(res?.data) ? res.data : [];
          const sanitize = (v: any) => {
            if (!v) return '';
            try { v = String(v); } catch(e) { return ''; }
            v = v.replace(/[^A-Za-zÀ-ÿ\s\-]/g, ' ').replace(/\s+/g, ' ').trim();
            if (!v || /\d/.test(v) || v.length < 2) return '';
            return v.toLowerCase();
          };
          let mapped = raw.map((z: any) => ({
            ...z,
            zone_label: sanitize(z.zone_label) || sanitize(z.ville) || sanitize(z.gouvernorat) || '',
            ville: sanitize(z.ville) || '',
            gouvernorat: sanitize(z.gouvernorat) || '',
          }));
          // remove empty labels, sort by score desc, and title-case labels
          mapped = mapped.filter((z: any) => z.zone_label && z.zone_label.length > 0);
          mapped.sort((a: any, b: any) => (b.score_roi || 0) - (a.score_roi || 0));
          mapped.forEach((z: any) => { z.zone_label = this.titleCase(z.zone_label); });
          this.topZones = mapped;
          this.zonesLoading = false;
        },
        error: () => {
          this.topZones = [];
          this.zonesLoading = false;
        }
      });
  }

  titleCase(s: string): string {
    return s.replace(/\w\S*/g, (txt) => txt.charAt(0).toUpperCase() + txt.substr(1));
  }
}