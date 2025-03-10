import json
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field, validator

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
    
    REQUIRED_FIELDS = {
        "BASE": ["title", "description", "discipline", "availability", "seniority", "languages", "skills", "jobType", "type"],
        "FREELANCE": ["minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks"],
        "FULLTIME": ["minFullTimeSalary", "maxFullTimeSalary"],
        "PARTTIME": ["minPartTimeSalary", "maxPartTimeSalary"],
        "REMOTE": ["continents", "countries", "regions", "timeZone"],
        "ONSITE_HYBRID": ["country", "city"]
    }

    GEOGRAPHIC_RELATIONS = {
        "continents": {
            "europe": ["france", "espagne", "allemagne", "italie", "ukraine", "royaume-uni", "suisse", "belgique"],
            "amérique du nord": ["usa", "canada", "mexique"],
            "amérique du sud": ["brésil", "argentine", "chili", "colombie", "pérou"],
            "asie": ["japon", "chine", "inde", "singapour", "corée du sud"],
            "afrique": ["maroc", "algérie", "égypte", "afrique du sud", "tunisie"],
            "océanie": ["australie", "nouvelle-zélande"]
        },
        "countries": {
            "france": ["paris", "lyon", "marseille", "toulouse", "bordeaux", "lille", "nantes", "strasbourg"],
            "espagne": ["madrid", "barcelone", "valence", "séville", "malaga"], 
            "allemagne": ["berlin", "munich", "hambourg", "francfort", "cologne"],
            "usa": ["new york", "los angeles", "chicago", "san francisco", "boston", "seattle", "austin", "miami"],
            "maroc": ["casablanca", "rabat", "marrakech", "tanger", "fès"],
            "algérie": ["alger", "oran", "constantine"],
            "égypte": ["le caire", "alexandrie"],
            "canada": ["toronto", "montréal", "vancouver", "ottawa", "québec"],
            "mexique": ["mexico", "guadalajara", "monterrey"],
            "royaume-uni": ["londres", "manchester", "édimbourg", "birmingham"],
            "japon": ["tokyo", "osaka", "kyoto"],
            "chine": ["pékin", "shanghai", "hong kong", "shenzhen"]
        }
    }

    def __init__(self):
        self.data = {"jobDetails": JobDetail().dict()}
        self._model = JobDetail()
    
    def update(self, key: str, value: Any) -> Tuple[bool, Optional[str]]:
        if key not in self.data["jobDetails"]:
            return False, f"⚠️ Champ '{key}' non valide."
        details = self.data["jobDetails"]
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
        base_fields = self.REQUIRED_FIELDS["BASE"]
        for field in base_fields:
            if not self.data["jobDetails"].get(field):
                missing.append(field)
        job_type = self.data["jobDetails"].get("jobType")
        if job_type in self.REQUIRED_FIELDS:
            for field in self.REQUIRED_FIELDS[job_type]:
                if not self.data["jobDetails"].get(field):
                    missing.append(field)
        type_field = self.data["jobDetails"].get("type")
        if type_field == "REMOTE":
            for field in self.REQUIRED_FIELDS["REMOTE"]:
                if not self.data["jobDetails"].get(field):
                    missing.append(field)
        elif type_field in ["ONSITE", "HYBRID"]:
            for field in self.REQUIRED_FIELDS["ONSITE_HYBRID"]:
                if not self.data["jobDetails"].get(field):
                    missing.append(field)
        return missing

    def get_state(self) -> Dict[str, Any]:
        return self.data

    def validate_coherence(self) -> Tuple[bool, Optional[str]]:
        return True, None