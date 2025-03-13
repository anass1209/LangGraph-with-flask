import json
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field, validator
import pycountry  # Ajout de l'importation de pycountry

class JobDetail(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    discipline: Optional[str] = None
    availability: Optional[float] = None  # en semaines
    seniority: Optional[str] = None      # JUNIOR, MID, SENIOR
    languages: List[Dict[str, Any]] = Field(default_factory=list)
    skills: List[Dict[str, Any]] = Field(default_factory=list)
    type: Optional[str] = None           # REMOTE, ONSITE, HYBRID
    jobType: Optional[str] = None        # FREELANCE, FULLTIME, PARTTIME
    countries: List[Dict[str, str]] = Field(default_factory=list)
    continents: List[Dict[str, str]] = Field(default_factory=list)
    regions: List[Dict[str, str]] = Field(default_factory=list)
    timeZone: Dict[str, Any] = Field(default_factory=lambda: {"name": None, "overlap": None})
    country: Dict[str, Optional[str]] = Field(default_factory=lambda: {"name": None})
    city: Optional[str] = None
    minHourlyRate: Optional[float] = None
    maxHourlyRate: Optional[float] = None
    weeklyHours: Optional[float] = None
    estimatedWeeks: Optional[float] = None
    minFullTimeSalary: Optional[float] = None
    maxFullTimeSalary: Optional[float] = None
    minPartTimeSalary: Optional[float] = None
    maxPartTimeSalary: Optional[float] = None

    @validator('seniority')
    def validate_seniority(cls, v):
        if v and v not in ["JUNIOR", "MID", "SENIOR"]:
            raise ValueError(f"Seniority doit être JUNIOR, MID ou SENIOR, pas {v}")
        return v

    @validator('type')
    def validate_type(cls, v):
        if v and v not in ["REMOTE", "ONSITE", "HYBRID"]:
            raise ValueError(f"Type doit être REMOTE, ONSITE ou HYBRID, pas {v}")
        return v

    @validator('jobType')
    def validate_job_type(cls, v):
        if v and v not in ["FREELANCE", "FULLTIME", "PARTTIME"]:
            raise ValueError(f"JobType doit être FREELANCE, FULLTIME ou PARTTIME, pas {v}")
        return v

    @validator('availability')
    def validate_availability(cls, v):
        if v is not None and v < 0:
            raise ValueError("Availability ne peut pas être négative")
        return v

class JobDetails:
    JOB_TYPES = {"FREELANCE", "FULLTIME", "PARTTIME"}
    WORK_TYPES = {"REMOTE", "ONSITE", "HYBRID"}
    SENIORITY_LEVELS = {"JUNIOR", "MID", "SENIOR"}
    
    # Champs de base requis pour tous les types de job
    REQUIRED_FIELDS = {
        "BASE": ["title", "description", "discipline", "availability", "seniority", "languages", "skills", "jobType", "type"],
        # Champs requis selon le type d'emploi (jobType)
        "FREELANCE": ["minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks"],
        "FULLTIME": ["minFullTimeSalary", "maxFullTimeSalary"],
        "PARTTIME": ["minPartTimeSalary", "maxPartTimeSalary"],
        # Champs requis selon le type de travail (type)
        "REMOTE": ["continents", "countries", "regions", "timeZone"],
        "ONSITE": ["country", "city"],
        "HYBRID": ["country", "city"]
    }

    VALID_CONTINENTS = ["Europe", "Asie", "Amérique du Nord", "Amérique du Sud", "Afrique", "Océanie"]

    def __init__(self):
        self.data = {"jobDetails": JobDetail().dict()}
        self._model = JobDetail()
    
    def update(self, key: str, value: Any) -> Tuple[bool, Optional[str]]:
        if key not in self.data["jobDetails"]:
            return False, f"⚠️ Champ '{key}' non valide."
        details = self.data["jobDetails"]

        # Validation des champs géographiques avec pycountry
        if key == "continents" and isinstance(value, list):
            for continent_item in value:
                if isinstance(continent_item, dict) and "name" in continent_item:
                    continent_name = continent_item["name"]
                    if continent_name not in self.VALID_CONTINENTS:
                        try:
                            # Vérifier si c'est un pays mal interprété comme continent
                            pycountry.countries.search_fuzzy(continent_name)
                            return False, f"⚠️ '{continent_name}' semble être un pays, pas un continent."
                        except LookupError:
                            return False, f"⚠️ Le continent '{continent_name}' n'est pas valide. Options: {', '.join(self.VALID_CONTINENTS)}"

        if key == "countries" and isinstance(value, list):
            validated_countries = []
            for country_item in value:
                if isinstance(country_item, dict) and "name" in country_item:
                    country_name = country_item["name"].lower()
                    try:
                        country = pycountry.countries.search_fuzzy(country_name)[0]
                        validated_countries.append({"name": country.name})
                    except LookupError:
                        return False, f"⚠️ Le pays '{country_name}' n'est pas valide."
            # Vérifier la cohérence avec les continents existants
            if details.get("continents"):
                continents = [c["name"].lower() for c in details["continents"] if isinstance(c, dict) and "name" in c]
                continent_map = {
                    "europe": "EU",
                    "asie": "AS",
                    "amérique du nord": "NA",
                    "amérique du sud": "SA",
                    "afrique": "AF",
                    "océanie": "OC"
                }
                for country_item in validated_countries:
                    country_name = country_item["name"].lower()
                    country = pycountry.countries.search_fuzzy(country_name)[0]
                    country_continent = country.continent if hasattr(country, 'continent') else None
                    if country_continent and not any(continent_map.get(continent) == country_continent for continent in continents):
                        return False, f"⚠️ Le pays '{country_name}' n'est pas dans les continents: {continents}"
            value = validated_countries  # Remplacer par les noms validés

        if key == "regions" and isinstance(value, list):
            validated_regions = []
            countries = [c["name"].lower() for c in details.get("countries", []) if isinstance(c, dict) and "name" in c]
            for region_item in value:
                if isinstance(region_item, dict) and "name" in region_item:
                    region_name = region_item["name"].lower()
                    if countries:
                        found = False
                        for country_name in countries:
                            try:
                                country = pycountry.countries.search_fuzzy(country_name)[0]
                                subdivisions = list(pycountry.subdivisions.get(country_code=country.alpha_2))
                                for subdiv in subdivisions:
                                    if region_name in subdiv.name.lower() or region_name == subdiv.code.lower():
                                        validated_regions.append({"name": subdiv.name})
                                        found = True
                                        break
                                if found:
                                    break
                            except LookupError:
                                continue
                        if not found:
                            return False, f"⚠️ La région '{region_name}' n'est pas valide pour les pays: {countries}"
                    else:
                        # Si aucun pays n'est spécifié, accepter la région telle quelle
                        validated_regions.append({"name": region_item["name"]})
            value = validated_regions  # Remplacer par les noms validés

        # Validation existante conservée
        if key == "countries" and isinstance(value, list) and details.get("continents"):
            continents = [c["name"].lower() for c in details["continents"] if isinstance(c, dict) and "name" in c]
            for country_item in value:
                if isinstance(country_item, dict) and "name" in country_item:
                    country_name = country_item["name"].lower()
                    if not any(country_name in self.GEOGRAPHIC_RELATIONS["continents"].get(continent, []) for continent in continents):
                        return False, f"⚠️ Le pays '{country_name}' n'est pas dans les continents: {continents}"
        if key == "regions" and isinstance(value, list) and details.get("countries"):
            countries = [c["name"].lower() for c in details["countries"] if isinstance(c, dict) and "name" in c]
            for region_item in value:
                if isinstance(region_item, dict) and "name" in region_item:
                    region_name = region_item["name"].lower()
                    if not any(region_name in self.GEOGRAPHIC_RELATIONS["countries"].get(country, []) for country in countries):
                        return False, f"⚠️ La région '{region_name}' n'est pas dans les pays: {countries}"
        if key in ["minHourlyRate", "maxHourlyRate"] and details.get("minHourlyRate") is not None and details.get("maxHourlyRate") is not None:
            if details["minHourlyRate"] > details["maxHourlyRate"]:
                return False, "⚠️ Le taux horaire minimum ne peut pas dépasser le maximum."
        if key in ["minFullTimeSalary", "maxFullTimeSalary"] and details.get("minFullTimeSalary") is not None and details.get("maxFullTimeSalary") is not None:
            if details["minFullTimeSalary"] > details["maxFullTimeSalary"]:
                return False, "⚠️ Le salaire minimum ne peut pas dépasser le maximum."
        if key == "weeklyHours" and value is not None and value > 168:
            return False, "⚠️ Les heures par semaine ne peuvent pas dépasser 168."
        if key == "availability" and value is not None and value < 0:
            return False, "⚠️ La disponibilité ne peut pas être négative."
        try:
            if key in ["languages", "skills"] and isinstance(value, dict):
                if key == "languages" and not all(k in value for k in ["name", "level", "required"]):
                    return False, f"⚠️ L'objet pour '{key}' doit inclure 'name', 'level', 'required'."
                if key == "skills" and not all(k in value for k in ["name", "mandatory"]):
                    return False, f"⚠️ L'objet pour '{key}' doit inclure 'name', 'mandatory'."
            details[key] = value
            return True, None
        except Exception as e:
            return False, f"Erreur lors de la mise à jour: {e}"

    def get_missing_fields(self) -> List[str]:
        missing = []
        details = self.data["jobDetails"]
        
        # Vérifier les champs de base
        for field in self.REQUIRED_FIELDS["BASE"]:
            if not details.get(field):
                missing.append(field)
        
        # Obtenir le type de travail et d'emploi
        job_type = details.get("jobType")
        work_type = details.get("type")
        
        # Vérifier les champs spécifiques au type d'emploi (jobType)
        if job_type in self.JOB_TYPES:
            for field in self.REQUIRED_FIELDS.get(job_type, []):
                if not details.get(field):
                    missing.append(field)
        
        # Vérifier les champs spécifiques au type de travail (type)
        if work_type in self.WORK_TYPES:
            for field in self.REQUIRED_FIELDS.get(work_type, []):
                if not details.get(field):
                    missing.append(field)
                    
        return missing

    def get_state(self) -> Dict[str, Any]:
        return self.data

    def validate_coherence(self) -> Tuple[bool, Optional[str]]:
        details = self.data["jobDetails"]
        job_type = details.get("jobType")
        work_type = details.get("type")
        
        # Vérifier que le type d'emploi est valide
        if job_type and job_type not in self.JOB_TYPES:
            return False, f"⚠️ Type d'emploi '{job_type}' non valide. Valeurs acceptées: {', '.join(self.JOB_TYPES)}"
            
        # Vérifier que le type de travail est valide
        if work_type and work_type not in self.WORK_TYPES:
            return False, f"⚠️ Type de travail '{work_type}' non valide. Valeurs acceptées: {', '.join(self.WORK_TYPES)}"
            
        # Vérifier la cohérence des champs géographiques avec pycountry
        if work_type == "REMOTE":
            # Validation des continents
            if details.get("continents"):
                for continent_item in details["continents"]:
                    if isinstance(continent_item, dict) and "name" in continent_item:
                        continent_name = continent_item["name"]
                        if continent_name not in self.VALID_CONTINENTS:
                            return False, f"⚠️ Le continent '{continent_name}' n'est pas valide. Options: {', '.join(self.VALID_CONTINENTS)}"

            # Vérifier que les pays sont cohérents avec les continents
            if details.get("countries") and details.get("continents"):
                continents = [c["name"].lower() for c in details["continents"] if isinstance(c, dict) and "name" in c]
                continent_map = {
                    "europe": "EU",
                    "asie": "AS",
                    "amérique du nord": "NA",
                    "amérique du sud": "SA",
                    "afrique": "AF",
                    "océanie": "OC"
                }
                for country_item in details["countries"]:
                    if isinstance(country_item, dict) and "name" in country_item:
                        country_name = country_item["name"].lower()
                        try:
                            country = pycountry.countries.search_fuzzy(country_name)[0]
                            country_continent = country.continent if hasattr(country, 'continent') else None
                            if country_continent and not any(continent_map.get(continent) == country_continent for continent in continents):
                                return False, f"⚠️ Le pays '{country_name}' n'est pas dans les continents spécifiés: {continents}"
                        except LookupError:
                            return False, f"⚠️ Le pays '{country_name}' n'est pas valide."

            # Vérifier que les régions sont cohérentes avec les pays
            if details.get("regions") and details.get("countries"):
                countries = [c["name"].lower() for c in details["countries"] if isinstance(c, dict) and "name" in c]
                for region_item in details["regions"]:
                    if isinstance(region_item, dict) and "name" in region_item:
                        region_name = region_item["name"].lower()
                        found = False
                        for country_name in countries:
                            try:
                                country = pycountry.countries.search_fuzzy(country_name)[0]
                                subdivisions = list(pycountry.subdivisions.get(country_code=country.alpha_2))
                                for subdiv in subdivisions:
                                    if region_name in subdiv.name.lower() or region_name == subdiv.code.lower():
                                        found = True
                                        break
                                if found:
                                    break
                            except LookupError:
                                continue
                        if not found:
                            return False, f"⚠️ La région '{region_name}' n'est pas dans les pays spécifiés: {countries}"

        # Vérifier les taux ou salaires min/max
        if job_type == "FREELANCE":
            if details.get("minHourlyRate") is not None and details.get("maxHourlyRate") is not None:
                if details["minHourlyRate"] > details["maxHourlyRate"]:
                    return False, "⚠️ Le taux horaire minimum ne peut pas dépasser le maximum."
        elif job_type == "FULLTIME":
            if details.get("minFullTimeSalary") is not None and details.get("maxFullTimeSalary") is not None:
                if details["minFullTimeSalary"] > details["maxFullTimeSalary"]:
                    return False, "⚠️ Le salaire minimum ne peut pas dépasser le maximum."
        elif job_type == "PARTTIME":
            if details.get("minPartTimeSalary") is not None and details.get("maxPartTimeSalary") is not None:
                if details["minPartTimeSalary"] > details["maxPartTimeSalary"]:
                    return False, "⚠️ Le salaire minimum ne peut pas dépasser le maximum."
                    
        return True, None