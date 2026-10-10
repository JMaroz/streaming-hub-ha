"""Unit tests for rating filter, adult content detection, and crawler age classification."""

from __future__ import annotations

from streaming_hub.backend.crawler_parser import CrawlerCatalogParser
from streaming_hub.backend.models import Movie, Profile
from streaming_hub.backend.rating_filter import get_profile_max_rating, is_title_allowed_for_profile


class TestRatingFilter:
    """Test suite for rating filter rules and profile safety."""

    def setup_method(self, method=None) -> None:
        """Set up test profile instances."""
        self.profile_t = Profile(id="p_t", name="Bambini T", rating_filter="T")
        self.profile_6 = Profile(id="p_6", name="Bambini 6+", rating_filter="6+")
        self.profile_12 = Profile(id="p_12", name="Pre-teen 12+", rating_filter="12+")
        self.profile_14 = Profile(id="p_14", name="Teen 14+", rating_filter="14+")
        self.profile_18 = Profile(id="p_18", name="Adult 18+", rating_filter="18+")

    def test_get_profile_max_rating(self) -> None:
        """Test parsing profile rating filters to numeric thresholds."""
        assert get_profile_max_rating(self.profile_t) == 0
        assert get_profile_max_rating(self.profile_6) == 6
        assert get_profile_max_rating(self.profile_12) == 12
        assert get_profile_max_rating(self.profile_14) == 14
        assert get_profile_max_rating(self.profile_18) == 18
        assert get_profile_max_rating(Profile(id="p_all", name="All", rating_filter="ALL")) == 99

    def test_explicit_adult_flag_blocked(self) -> None:
        """Test that items with is_adult=True are blocked on any profile < 18."""
        adult_movie = Movie(id="m_adult", title="Titolo Generico", is_adult=True)
        assert not is_title_allowed_for_profile(adult_movie, self.profile_t)
        assert not is_title_allowed_for_profile(adult_movie, self.profile_6)
        assert not is_title_allowed_for_profile(adult_movie, self.profile_14)
        assert is_title_allowed_for_profile(adult_movie, self.profile_18)

    def test_certification_vm18_blocked(self) -> None:
        """Test that certification VM18 is blocked on any profile < 18."""
        vm18_movie = Movie(id="m_vm18", title="Pellicola Drammatica", certification="VM18")
        assert not is_title_allowed_for_profile(vm18_movie, self.profile_t)
        assert not is_title_allowed_for_profile(vm18_movie, self.profile_6)
        assert not is_title_allowed_for_profile(vm18_movie, self.profile_14)
        assert is_title_allowed_for_profile(vm18_movie, self.profile_18)

    def test_adult_franchises_blocked(self) -> None:
        """Test that famous adult/erotic titles and franchises are blocked on minor profiles."""
        adult_titles = [
            Movie(id="a1", title="365 Giorni", genres=["Drammatico"]),
            Movie(id="a2", title="365 Days: This Day", genres=["Drama"]),
            Movie(id="a3", title="Cinquanta Sfumature di Grigio", genres=["Drammatico", "Romantico"]),
            Movie(id="a4", title="Fifty Shades Freed", genres=["Drama", "Romance"]),
            Movie(id="a5", title="Nymphomaniac: Vol. I", genres=["Drammatico"]),
            Movie(id="a6", title="Kamasutra 3D", genres=["Drammatico"]),
            Movie(id="a7", title="Lucia y el sexo", genres=["Drammatico"]),
            Movie(id="a8", title="Desideri Proibiti", genres=["Erotico"]),
            Movie(id="a9", title="Peccati di Famiglia", genres=["Drammatico"]),
            Movie(id="a10", title="Malizia", genres=["Commedia"]),
        ]
        for m in adult_titles:
            if True:
                assert not is_title_allowed_for_profile(m, self.profile_t)
                assert not is_title_allowed_for_profile(m, self.profile_6)
                assert not is_title_allowed_for_profile(m, self.profile_14)
                assert is_title_allowed_for_profile(m, self.profile_18)

    def test_uncertified_unfriendly_content_excluded_on_kids_profiles(self) -> None:
        """Test that uncertified content without family tags is excluded on Kids (T and 6+) profiles."""
        uncertified_items = [
            Movie(id="u1", title="Casalinghe disperate", description="", genres=[]),
            Movie(id="u2", title="Film Sospetto Sconosciuto", description="", genres=[]),
            Movie(id="u3", title="Dramma Familiare Intenso", description="Un dramma", genres=["Drammatico"]),
        ]
        for item in uncertified_items:
            if True:
                assert not is_title_allowed_for_profile(item, self.profile_t)
                assert not is_title_allowed_for_profile(item, self.profile_6)

    def test_safe_family_titles_allowed_on_kids_profiles(self) -> None:
        """Test that safe family titles and franchises pass for Kids profiles."""
        safe_items = [
            Movie(id="s1", title="Il Re Leone", genres=["Animazione", "Famiglia"]),
            Movie(id="s2", title="Frozen - Il regno di ghiaccio", genres=["Animazione", "Famiglia"]),
            Movie(id="s3", title="Paw Patrol: Il film", genres=["Animazione", "Kids"]),
            Movie(id="s4", title="Peppa Pig", genres=["Animazione", "Bambini"]),
            Movie(id="s5", title="Harry Potter e la Pietra Filosofale", genres=["Avventura", "Fantasy", "Famiglia"]),
        ]
        for item in safe_items:
            assert is_title_allowed_for_profile(item, self.profile_t)
            assert is_title_allowed_for_profile(item, self.profile_6)
            assert is_title_allowed_for_profile(item, self.profile_14)

    def test_paw_patrol_and_super_mario_allowed_on_kids_profiles(self) -> None:
        """Test that PAW Patrol: Missione Natale and Super Mario Galaxy are allowed on T and 6+ profiles."""
        # Paw Patrol with mystery plot and uncertified or T cert
        paw_patrol = Movie(
            id="paw-xmas",
            title="PAW Patrol: Missione Natale",
            genres=["Animazione", "Famiglia", "Avventura"],
            description="Babbo Natale si ammala e Rubble deve svelare il mistero per salvare i regali dal sindaco Humdinger.",
            certification=None,
        )
        assert is_title_allowed_for_profile(paw_patrol, self.profile_t)
        assert is_title_allowed_for_profile(paw_patrol, self.profile_6)

        # Super Mario Galaxy with space conflict plot and PG certification
        mario_galaxy = Movie(
            id="mario-galaxy",
            title="The Super Mario Galaxy Movie",
            genres=["Animazione", "Avventura", "Commedia", "Famiglia"],
            description="Mario e Luigi affrontano una guerra galattica per salvare Rosalina da Bowser Jr.",
            certification="PG",
        )
        assert is_title_allowed_for_profile(mario_galaxy, self.profile_t)
        assert is_title_allowed_for_profile(mario_galaxy, self.profile_6)

        # Super Mario Galaxy with uncertified status
        mario_uncertified = Movie(
            id="mario-galaxy-raw",
            title="Super Mario Galaxy",
            genres=["Animazione", "Avventura"],
            description="Avventura spaziale contro Bowser.",
            certification=None,
        )
        assert is_title_allowed_for_profile(mario_uncertified, self.profile_t)
        assert is_title_allowed_for_profile(mario_uncertified, self.profile_6)

    def test_hotel_transylvania_not_blocked_by_hot(self) -> None:
        """Test that Hotel Transylvania is not falsely blocked by 'hot' adult keyword."""
        hotel = Movie(
            id="hotel-1",
            title="Hotel Transylvania",
            genres=["Animazione", "Commedia", "Famiglia"],
            description="Benvenuti all'Hotel Transylvania, il sontuoso resort di Dracula per mostri.",
            certification="PG",
        )
        assert is_title_allowed_for_profile(hotel, self.profile_t)
        assert is_title_allowed_for_profile(hotel, self.profile_6)

    def test_coming_of_age_and_awards_not_blocked_by_false_positives(self) -> None:
        """Test that plots with 'diventa adulto', 'award', and 'giallo' pass on kids profiles."""
        lion_king = Movie(
            id="lk-1",
            title="Il Re Leone",
            genres=["Animazione", "Famiglia"],
            description="Simba cresce nella savana e diventa adulto per affrontare lo zio Scar. Vincitore di Academy Awards.",
            certification="T",
        )
        assert is_title_allowed_for_profile(lion_king, self.profile_t)
        assert is_title_allowed_for_profile(lion_king, self.profile_6)

        minions = Movie(
            id="minions-1",
            title="Minions",
            genres=["Animazione", "Commedia", "Famiglia"],
            description="Piccoli esseri gialli alla ricerca di un padrone malvagio.",
            certification="PG",
        )
        assert is_title_allowed_for_profile(minions, self.profile_t)
        assert is_title_allowed_for_profile(minions, self.profile_6)

        zootropolis = Movie(
            id="zoo-1",
            title="Zootropolis",
            genres=["Animazione", "Commedia", "Crime", "Famiglia"],
            description="La coniglietta poliziotto Judy Hopps risolve un crimine misterioso.",
            certification="PG",
        )
        assert is_title_allowed_for_profile(zootropolis, self.profile_t)
        assert is_title_allowed_for_profile(zootropolis, self.profile_6)

    def test_crawler_parser_extracts_age_certification(self) -> None:
        """Test that CrawlerCatalogParser extracts age certifications from HTML and title tags."""
        clean_title, year, quality, cert = CrawlerCatalogParser.clean_title("Film Proibito [VM18] (2023) [HD]")
        assert clean_title == "Film Proibito"
        assert year == 2023
        assert quality == "HD"
        assert cert == "VM18"

        clean_title2, _, _, cert2 = CrawlerCatalogParser.clean_title("Azione Violenta 14+ Streaming")
        assert clean_title2 == "Azione Violenta"
        assert cert2 == "14+"

        _genres, duration, _country, meta_cert = CrawlerCatalogParser.parse_metadata_line("DURATA 120m - ITALIA - VM18")
        assert meta_cert == "VM18"
        assert duration == 120
