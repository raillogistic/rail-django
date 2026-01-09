"""
Commande de gestion Django pour exécuter les benchmarks de performance.

Cette commande permet d'exécuter facilement les benchmarks de performance
depuis la ligne de commande avec diverses options de configuration.
"""

import os
import sys

from benchmarks.performance_benchmarks import (
    PerformanceBenchmark,
    run_full_benchmark_suite,
)
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """
    Commande Django pour exécuter les benchmarks de performance.

    Usage:
        python manage.py run_performance_benchmarks
        python manage.py run_performance_benchmarks --test n_plus_one
        python manage.py run_performance_benchmarks --output-dir ./results
        python manage.py run_performance_benchmarks --data-sizes 10,50,100
    """

    help = "Exécute les benchmarks de performance pour Django GraphQL Auto"

    def add_arguments(self, parser):
        """Ajoute les arguments de la commande."""
        parser.add_argument(
            "--test",
            type=str,
            choices=["n_plus_one", "caching", "load", "complexity", "all"],
            default="all",
            help="Type de test à exécuter (défaut: all)",
        )

        parser.add_argument(
            "--output-dir",
            type=str,
            default="benchmark_results",
            help="Répertoire de sortie pour les résultats (défaut: benchmark_results)",
        )

        parser.add_argument(
            "--data-sizes",
            type=str,
            default="10,50,100",
            help="Tailles de données pour les tests N+1 (défaut: 10,50,100)",
        )

        parser.add_argument(
            "--concurrent-users",
            type=str,
            default="1,5,10",
            help="Nombres d'utilisateurs concurrents pour les tests de charge (défaut: 1,5,10)",
        )

        parser.add_argument(
            "--requests-per-user",
            type=int,
            default=10,
            help="Nombre de requêtes par utilisateur pour les tests de charge (défaut: 10)",
        )

        parser.add_argument(
            "--query-depths",
            type=str,
            default="1,3,5",
            help="Profondeurs de requêtes pour les tests de complexité (défaut: 1,3,5)",
        )

        parser.add_argument(
            "--cache-scenarios",
            type=str,
            default="no_cache,query_cache,field_cache,full_cache",
            help="Scénarios de cache à tester (défaut: no_cache,query_cache,field_cache,full_cache)",
        )

        parser.add_argument(
            "--verbose", action="store_true", help="Affichage verbeux des résultats"
        )

        parser.add_argument(
            "--no-cleanup",
            action="store_true",
            help="Ne pas nettoyer les données de test après les benchmarks",
        )

    def handle(self, *args, **options):
        """Exécute la commande."""
        self.stdout.write(
            self.style.SUCCESS("🚀 Démarrage des benchmarks de performance...")
        )

        # Vérifier la configuration
        self._check_configuration()

        # Créer l'instance de benchmark
        benchmark = PerformanceBenchmark(output_dir=options["output_dir"])

        try:
            # Exécuter les tests selon les options
            if options["test"] == "all":
                self._run_all_benchmarks(benchmark, options)
            elif options["test"] == "n_plus_one":
                self._run_n_plus_one_benchmark(benchmark, options)
            elif options["test"] == "caching":
                self._run_caching_benchmark(benchmark, options)
            elif options["test"] == "load":
                self._run_load_benchmark(benchmark, options)
            elif options["test"] == "complexity":
                self._run_complexity_benchmark(benchmark, options)

            # Générer le rapport
            summary = benchmark.generate_report()

            # Afficher les résultats
            self._display_results(summary, options["verbose"])

            self.stdout.write(self.style.SUCCESS("✅ Benchmarks terminés avec succès!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Erreur lors des benchmarks: {e}"))
            if options["verbose"]:
                import traceback

                self.stdout.write(traceback.format_exc())
            raise CommandError(f"Échec des benchmarks: {e}")

    def _check_configuration(self):
        """Vérifie la configuration Django."""
        # Vérifier que les apps nécessaires sont installées
        required_apps = [
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "rail_django",
        ]

        for app in required_apps:
            if app not in settings.INSTALLED_APPS:
                raise CommandError(f"App requise manquante: {app}")

        # Vérifier la configuration de la base de données
        if not settings.DATABASES:
            raise CommandError("Configuration de base de données manquante")

        # Vérifier la configuration du cache
        if not hasattr(settings, "CACHES"):
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Configuration de cache manquante, utilisation du cache par défaut"
                )
            )

    def _parse_int_list(self, value: str) -> list:
        """Parse une liste d'entiers séparés par des virgules."""
        try:
            return [int(x.strip()) for x in value.split(",")]
        except ValueError as e:
            raise CommandError(f"Format de liste invalide: {value}. Erreur: {e}")

    def _parse_string_list(self, value: str) -> list:
        """Parse une liste de chaînes séparées par des virgules."""
        return [x.strip() for x in value.split(",")]

    def _run_all_benchmarks(self, benchmark: PerformanceBenchmark, options: dict):
        """Exécute tous les benchmarks."""
        self.stdout.write("📊 Exécution de tous les benchmarks...")

        # N+1 benchmark
        data_sizes = self._parse_int_list(options["data_sizes"])
        benchmark.run_n_plus_one_benchmark(data_sizes)

        # Caching benchmark
        cache_scenarios = self._parse_string_list(options["cache_scenarios"])
        benchmark.run_caching_benchmark(cache_scenarios)

        # Load test
        concurrent_users = self._parse_int_list(options["concurrent_users"])
        benchmark.run_load_test(concurrent_users, options["requests_per_user"])

        # Complexity benchmark
        query_depths = self._parse_int_list(options["query_depths"])
        benchmark.run_complexity_benchmark(query_depths)

    def _run_n_plus_one_benchmark(self, benchmark: PerformanceBenchmark, options: dict):
        """Exécute le benchmark N+1."""
        self.stdout.write("📊 Exécution du benchmark N+1...")
        data_sizes = self._parse_int_list(options["data_sizes"])
        benchmark.run_n_plus_one_benchmark(data_sizes)

    def _run_caching_benchmark(self, benchmark: PerformanceBenchmark, options: dict):
        """Exécute le benchmark de cache."""
        self.stdout.write("📊 Exécution du benchmark de cache...")
        cache_scenarios = self._parse_string_list(options["cache_scenarios"])
        benchmark.run_caching_benchmark(cache_scenarios)

    def _run_load_benchmark(self, benchmark: PerformanceBenchmark, options: dict):
        """Exécute le test de charge."""
        self.stdout.write("📊 Exécution du test de charge...")
        concurrent_users = self._parse_int_list(options["concurrent_users"])
        benchmark.run_load_test(concurrent_users, options["requests_per_user"])

    def _run_complexity_benchmark(self, benchmark: PerformanceBenchmark, options: dict):
        """Exécute le benchmark de complexité."""
        self.stdout.write("📊 Exécution du benchmark de complexité...")
        query_depths = self._parse_int_list(options["query_depths"])
        benchmark.run_complexity_benchmark(query_depths)

    def _display_results(self, summary, verbose: bool):
        """Affiche les résultats des benchmarks."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("📊 RÉSULTATS DES BENCHMARKS"))
        self.stdout.write("=" * 60)

        # Résumé principal
        self.stdout.write(f"Tests total: {summary.total_tests}")
        self.stdout.write(self.style.SUCCESS(f"Succès: {summary.successful_tests}"))
        if summary.failed_tests > 0:
            self.stdout.write(self.style.ERROR(f"Échecs: {summary.failed_tests}"))

        self.stdout.write(f"Temps d'exécution moyen: {summary.avg_execution_time:.3f}s")
        self.stdout.write(f"Temps minimum: {summary.min_execution_time:.3f}s")
        self.stdout.write(f"Temps maximum: {summary.max_execution_time:.3f}s")

        # Métriques de performance
        self.stdout.write("\n📈 MÉTRIQUES DE PERFORMANCE:")
        self.stdout.write(
            f"Requêtes de base de données: {summary.total_database_queries}"
        )
        self.stdout.write(f"Cache hits: {summary.total_cache_hits}")
        self.stdout.write(f"Cache misses: {summary.total_cache_misses}")

        # Amélioration des performances
        if summary.performance_improvement > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n🚀 AMÉLIORATION DES PERFORMANCES: {summary.performance_improvement:.1f}%"
                )
            )
        elif summary.performance_improvement < 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  DÉGRADATION DES PERFORMANCES: {abs(summary.performance_improvement):.1f}%"
                )
            )
        else:
            self.stdout.write("\n➡️  Aucune amélioration mesurable des performances")

        # Recommandations
        self._display_recommendations(summary)

        # Informations sur les fichiers de sortie
        self.stdout.write(f"\n📁 Résultats sauvegardés dans: benchmark_results/")
        self.stdout.write("   - benchmark_results_*.json (données détaillées)")
        self.stdout.write("   - benchmark_results_*.csv (format tableur)")
        self.stdout.write("   - benchmark_report_*.html (rapport visuel)")

    def _display_recommendations(self, summary):
        """Affiche des recommandations basées sur les résultats."""
        self.stdout.write("\n💡 RECOMMANDATIONS:")

        # Recommandations basées sur les performances
        if summary.performance_improvement < 10:
            self.stdout.write("• Considérez l'activation de plus d'optimisations")
            self.stdout.write("• Vérifiez la configuration du cache")

        if summary.total_database_queries > summary.successful_tests * 2:
            self.stdout.write("• Nombre élevé de requêtes DB détecté")
            self.stdout.write(
                "• Vérifiez l'implémentation de select_related/prefetch_related"
            )

        cache_hit_ratio = 0
        if summary.total_cache_hits + summary.total_cache_misses > 0:
            cache_hit_ratio = summary.total_cache_hits / (
                summary.total_cache_hits + summary.total_cache_misses
            )

        if cache_hit_ratio < 0.5:
            self.stdout.write("• Taux de cache hit faible détecté")
            self.stdout.write("• Considérez l'ajustement de la stratégie de cache")

        if summary.avg_execution_time > 1.0:
            self.stdout.write("• Temps d'exécution élevé détecté")
            self.stdout.write("• Considérez l'optimisation des requêtes complexes")

        if summary.failed_tests > 0:
            self.stdout.write(
                self.style.WARNING("• Des tests ont échoué, vérifiez les logs")
            )

    def _cleanup_on_exit(self):
        """Nettoie les ressources à la sortie."""
        # Cette méthode peut être étendue pour nettoyer les données de test
        pass
