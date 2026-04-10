from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    bucket_name = "iqs-static"

    def url(self, name):
        return f"/static/{name}"


class MediaStorage(S3Boto3Storage):
    bucket_name = "iqs-media"

    def url(self, name):
        return f"/media/{name}"


class ReportStorage(S3Boto3Storage):
    bucket_name = "iqs-reports"


def get_report_storage():
    """Return a storage instance for the iqs-reports bucket."""
    return ReportStorage()
