import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  getAnnonces(collection: string, limit = 50, offset = 0): Observable<any> {
    const params = new HttpParams().set('collection', collection).set('limit', limit).set('offset', offset);
    return this.http.get(`${this.baseUrl}/api/annonces/`, { params });
  }

  getStats(): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/stats`);
  }

  estimateVente(params: HttpParams | { [key: string]: string | number }): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/vente/estimation`, { params });
  }

  getMapData(collection: string): Observable<any> {
    const params = new HttpParams().set('collection', collection).set('limit', 200);
    return this.http.get(`${this.baseUrl}/api/annonces/carte`, { params });
  }

  getAlertesNouvelles(): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/alertes/nouvelles`);
  }

  getAlertesPrix(): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/alertes/prix`);
  }

  getFiabiliteAlertes(): Observable<any> {
    return this.http.get(`${this.baseUrl}/api/fiabilite/alertes`);
  }
}
