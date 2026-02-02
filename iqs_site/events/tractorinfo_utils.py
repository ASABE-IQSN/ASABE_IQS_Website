from .models import TractorInfo

TRACTOR_INFO_MAP = {
    "instagram": TractorInfo.InfoTypes.INSTAGRAM,
    "facebook":  TractorInfo.InfoTypes.FACEBOOK,
    "website":   TractorInfo.InfoTypes.WEBSITE,
    "bio":       TractorInfo.InfoTypes.BIO,
    "nickname":  TractorInfo.InfoTypes.NICKNAME,
    "youtube":   TractorInfo.InfoTypes.YOUTUBE,
    "linkedin":  TractorInfo.InfoTypes.LINKEDIN,
}