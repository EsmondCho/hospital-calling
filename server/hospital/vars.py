from utils.enums import StrEnum


class HospitalSource(StrEnum):
    GOOGLE_PLACES = 'GOOGLE_PLACES'
    MANUAL = 'MANUAL'


class HospitalOwnership(StrEnum):
    """Mutually-exclusive ownership classification (DRT-5204 §1).

    A campaign can scope which clinics it targets by ownership.
    """

    INDEPENDENT = 'INDEPENDENT'          # solo / single-location practice
    CHAIN = 'CHAIN'                      # NVA, VetCor, Thrive, Petfolk, ...
    MARS_VH = 'MARS_VH'                  # Mars Veterinary Health (VCA / Banfield / BluePearl / Pet Partners)
    RETAIL_EMBEDDED = 'RETAIL_EMBEDDED'  # Petco Vetco, PetSmart Banfield, Walmart VIP Petcare
    NONPROFIT = 'NONPROFIT'              # SPCA, Humane Society, 501(c)(3) clinics
    UNIVERSITY = 'UNIVERSITY'            # vet-school teaching hospitals
    FRANCHISE = 'FRANCHISE'              # PetWellClinic, etc.
    UNCLASSIFIED = 'UNCLASSIFIED'        # default; LLM said NEEDS_REVIEW or info missing


class HospitalServiceTag(StrEnum):
    """Service offerings; multiple tags per hospital allowed (DRT-5204 §1).

    A multi-specialty ER is expressed as the combination
    `[SPECIALTY, EMERGENCY]` rather than its own tag. Specific specialty
    areas (cardiology, oncology, ...) go in `Hospital.specialty_areas`.
    """

    GENERAL_PRACTICE = 'GENERAL_PRACTICE'
    SPECIALTY = 'SPECIALTY'
    EMERGENCY = 'EMERGENCY'
    URGENT_CARE = 'URGENT_CARE'
    RETAIL_WELLNESS = 'RETAIL_WELLNESS'
    URGENT_WELLNESS = 'URGENT_WELLNESS'        # PetWellClinic-style walk-in wellness
    MOBILE_HOUSE_CALL = 'MOBILE_HOUSE_CALL'
    TELE_VET = 'TELE_VET'


class HospitalAppointmentMode(StrEnum):
    """Orthogonal to service tags: how the hospital takes patients."""

    APPOINTMENT_REQUIRED = 'APPOINTMENT_REQUIRED'
    WALK_IN_ALLOWED = 'WALK_IN_ALLOWED'
    WALK_IN_ONLY = 'WALK_IN_ONLY'
    UNKNOWN = 'UNKNOWN'
