"""Fixture data for Radarr API responses."""

from typing import Any

SYSTEM_STATUS_RESPONSE: dict[str, Any] = {
    "appName": "Radarr",
    "instanceName": "Radarr",
    "version": "5.2.6.8376",
    "buildTime": "2024-01-15T10:30:00Z",
    "isDebug": False,
    "isProduction": True,
    "isAdmin": True,
    "isUserInteractive": False,
    "startupPath": "/app/radarr/bin",
    "appData": "/config",
    "osName": "ubuntu",
    "osVersion": "22.04",
    "isMonoRuntime": False,
    "isMono": False,
    "isLinux": True,
    "isOsx": False,
    "isWindows": False,
    "mode": "console",
    "branch": "master",
    "authentication": "none",
    "sqliteVersion": "3.40.1",
    "migrationVersion": 216,
    "urlBase": "",
    "runtimeVersion": "8.0.1",
    "runtimeName": ".NET"
}

MOVIE_LOOKUP_RESPONSE: list[dict[str, Any]] = [
    {
        "title": "Dune: Part Two",
        "originalTitle": "Dune: Part Two",
        "originalLanguage": {
            "id": 1,
            "name": "English"
        },
        "alternateTitles": [],
        "secondaryYearSourceId": 0,
        "sortTitle": "dune part two",
        "sizeOnDisk": 0,
        "status": "released",
        "overview": "Follow the mythic journey of Paul Atreides as he unites with Chani and the Fremen while on a path of revenge against the conspirators who destroyed his family.",
        "inCinemas": "2024-02-29T00:00:00Z",
        "physicalRelease": "2024-05-14T00:00:00Z",
        "digitalRelease": "2024-04-16T00:00:00Z",
        "images": [
            {
                "coverType": "poster",
                "url": "https://image.tmdb.org/t/p/original/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg",
                "remoteUrl": "https://image.tmdb.org/t/p/original/1pdfLvkbY9ohJlCjQH2CZjjYVvJ.jpg"
            }
        ],
        "website": "",
        "year": 2024,
        "hasFile": False,
        "youTubeTrailerId": "",
        "studio": "Warner Bros. Pictures",
        "path": "",
        "qualityProfileId": 0,
        "monitored": False,
        "minimumAvailability": "announced",
        "isAvailable": True,
        "folderName": "",
        "runtime": 166,
        "cleanTitle": "dunepart2",
        "imdbId": "tt15239678",
        "tmdbId": 693134,
        "titleSlug": "dune-part-two-693134",
        "certification": "PG-13",
        "genres": ["Action", "Adventure", "Science Fiction"],
        "tags": [],
        "added": "0001-01-01T00:00:00Z",
        "ratings": {
            "imdb": {
                "votes": 89567,
                "value": 8.5,
                "type": "user"
            },
            "tmdb": {
                "votes": 1234,
                "value": 8.2,
                "type": "user"
            }
        },
        "movieFile": {
            "id": 0
        },
        "collection": {
            "name": "Dune Collection",
            "tmdbId": 726871,
            "images": []
        },
        "popularity": 324.567
    }
]

EMPTY_MOVIE_LOOKUP_RESPONSE: list[dict[str, Any]] = []

MOVIE_LIST_RESPONSE: list[dict[str, Any]] = [
    {
        "title": "The Matrix",
        "originalTitle": "The Matrix",
        "originalLanguage": {
            "id": 1,
            "name": "English"
        },
        "alternateTitles": [],
        "secondaryYearSourceId": 0,
        "sortTitle": "matrix",
        "sizeOnDisk": 2147483648,
        "status": "released",
        "overview": "A computer hacker learns from mysterious rebels about the true nature of his reality and his role in the war against its controllers.",
        "inCinemas": "1999-03-31T00:00:00Z",
        "images": [],
        "website": "",
        "year": 1999,
        "hasFile": True,
        "youTubeTrailerId": "",
        "studio": "Warner Bros.",
        "path": "/data/movies/The Matrix (1999)",
        "qualityProfileId": 1,
        "monitored": True,
        "minimumAvailability": "released",
        "isAvailable": True,
        "folderName": "The Matrix (1999)",
        "runtime": 136,
        "cleanTitle": "matrix",
        "imdbId": "tt0133093",
        "tmdbId": 603,
        "titleSlug": "the-matrix-603",
        "certification": "R",
        "genres": ["Action", "Science Fiction"],
        "tags": [1],
        "added": "2024-01-01T00:00:00Z",
        "ratings": {
            "imdb": {
                "votes": 1789456,
                "value": 8.7,
                "type": "user"
            }
        },
        "movieFile": {
            "id": 123,
            "movieId": 603,
            "relativePath": "The Matrix (1999) - Bluray-1080p.mkv",
            "path": "/data/movies/The Matrix (1999)/The Matrix (1999) - Bluray-1080p.mkv",
            "size": 2147483648,
            "dateAdded": "2024-01-01T12:00:00Z"
        },
        "collection": None,
        "popularity": 45.123,
        "id": 1
    }
]

ROOT_FOLDERS_RESPONSE: list[dict[str, Any]] = [
    {
        "id": 1,
        "path": "/data/movies",
        "accessible": True,
        "freeSpace": 1099511627776,
        "unmappedFolders": []
    }
]

QUALITY_PROFILES_RESPONSE: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "HD-1080p",
        "upgradeAllowed": True,
        "cutoff": 7,
        "items": [
            {
                "id": 1,
                "quality": {
                    "id": 1,
                    "name": "SDTV",
                    "source": "television",
                    "resolution": 480,
                    "modifier": "none"
                },
                "allowed": False
            },
            {
                "id": 7,
                "quality": {
                    "id": 7,
                    "name": "Bluray-1080p",
                    "source": "bluray",
                    "resolution": 1080,
                    "modifier": "none"
                },
                "allowed": True
            }
        ],
        "minFormatScore": 0,
        "cutoffFormatScore": 0,
        "formatItems": [],
        "language": {
            "id": 1,
            "name": "English"
        }
    }
]

ADD_MOVIE_SUCCESS_RESPONSE: dict[str, Any] = {
    "title": "Dune: Part Two",
    "originalTitle": "Dune: Part Two",
    "originalLanguage": {
        "id": 1,
        "name": "English"
    },
    "alternateTitles": [],
    "secondaryYearSourceId": 0,
    "sortTitle": "dune part two",
    "sizeOnDisk": 0,
    "status": "announced",
    "overview": "Follow the mythic journey of Paul Atreides as he unites with Chani and the Fremen while on a path of revenge against the conspirators who destroyed his family.",
    "inCinemas": "2024-02-29T00:00:00Z",
    "images": [],
    "website": "",
    "year": 2024,
    "hasFile": False,
    "youTubeTrailerId": "",
    "studio": "Warner Bros. Pictures",
    "path": "/data/movies/Dune Part Two (2024)",
    "qualityProfileId": 1,
    "monitored": True,
    "minimumAvailability": "announced",
    "isAvailable": False,
    "folderName": "",
    "runtime": 166,
    "cleanTitle": "dunepart2",
    "imdbId": "tt15239678",
    "tmdbId": 693134,
    "titleSlug": "dune-part-two-693134",
    "certification": "PG-13",
    "genres": ["Action", "Adventure", "Science Fiction"],
    "tags": [1],
    "added": "2024-09-19T16:00:00Z",
    "ratings": {
        "imdb": {
            "votes": 89567,
            "value": 8.5,
            "type": "user"
        }
    },
    "movieFile": {
        "id": 0
    },
    "collection": {
        "name": "Dune Collection",
        "tmdbId": 726871,
        "images": []
    },
    "popularity": 324.567,
    "id": 123
}

ADD_MOVIE_ERROR_RESPONSE: dict[str, Any] = {
    "propertyName": "tmdbId",
    "errorMessage": "This movie has already been added",
    "attemptedValue": 693134,
    "severity": "error",
    "errorCode": "MovieExistsValidator"
}