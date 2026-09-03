export interface PredictPayload {
  ville: string;
  quartier?: string;
  type_bien: string;
  surface: number;
  pieces?: number;
  chambres?: number;
  salles_bain?: number;
  haut_standing?: number;
  en_construction?: number;
}

export interface PredictResponse {
  prix_estime?: number;
  prix_min?: number;
  prix_max?: number;
  prix_par_m2?: number;
  ville?: string;
  quartier?: string;
  error?: string;
  model_version?: string;
}

export interface CitiesResponse {
  villes: string[];
}

export interface ApiStatusCheck {
  isAvailable: boolean;
  modelVersion?: string;
  message?: string;
}
