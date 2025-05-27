"""NLP Analyzer for the CJ Essay Assessment system.

This module computes various Natural Language Processing (NLP) statistics
for essay texts, such as word count, average word length, readability scores,
and more, using spaCy and textdescriptives. Results are stored in the database.
"""

from typing import Any

import spacy
# import textdescriptives as td  # Removed unused import
from loguru import logger

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db_handler import DatabaseHandler
from src.cj_essay_assessment.models_api import EssayForComparison
from src.cj_essay_assessment.models_db import ProcessedEssayStatusEnum

# Global spaCy nlp object - initialized by _ensure_spacy_model_loaded
NLP_MODEL: spacy.language.Language | None = None
SPACY_MODEL_NAME = "sv_core_news_sm"  # Or make this configurable via Settings
TEXTDESCRIPTIVES_PIPE_NAME = "textdescriptives/all"  # Use all standard components


async def _ensure_spacy_model_loaded(model_name: str = SPACY_MODEL_NAME) -> bool:
    """Ensures the spaCy language model is downloaded and loaded.
    Adds the textdescriptives pipeline component.
    Returns True if successful, False otherwise.
    """
    global NLP_MODEL
    # Check not only if a model is loaded, but if it has the required pipe
    if (
        NLP_MODEL is not None
        and NLP_MODEL.meta["name"] == model_name.split("_")[0]
        and TEXTDESCRIPTIVES_PIPE_NAME.split("/")[0]
        in NLP_MODEL.pipe_names  # Check if base pipe exists
    ):
        logger.debug(
            f"spaCy model '{NLP_MODEL.meta['lang']}_{NLP_MODEL.meta['name']}' "
            f"with '{TEXTDESCRIPTIVES_PIPE_NAME}' pipe already loaded.",
        )
        return True

    try:
        logger.info(f"Loading spaCy model '{model_name}'...")
        NLP_MODEL = spacy.load(model_name)

        # Add textdescriptives pipe if not already present
        if TEXTDESCRIPTIVES_PIPE_NAME.split("/")[0] not in NLP_MODEL.pipe_names:
            try:
                # Add all standard textdescriptives components
                NLP_MODEL.add_pipe(TEXTDESCRIPTIVES_PIPE_NAME)
                logger.info(f"Added '{TEXTDESCRIPTIVES_PIPE_NAME}' pipe to spaCy model.")
            except ValueError as ve:
                # Handle cases where a sub-component might already exist if adding 'all'
                if "already exists in pipeline" in str(ve):
                    logger.warning(
                        f"Some textdescriptives components might already exist: {ve}",
                    )
                    # Potentially try adding individual components if needed
                else:
                    raise ve  # Re-raise other ValueErrors
            except Exception as e:
                logger.error(
                    f"Failed to add '{TEXTDESCRIPTIVES_PIPE_NAME}' pipe: {e}. "
                    "NLP stats might be incomplete.",
                )
                # Decide if this is critical enough to return False (e.g., return False)

        logger.info(
            f"spaCy model '{model_name}' loaded successfully with TextDescriptives.",
        )
        return True
    except OSError:
        logger.error(
            f"spaCy model '{model_name}' not found. "
            f"Please download it by running: python -m spacy download {model_name}",
        )
        NLP_MODEL = None
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error loading spaCy model or adding pipe '{model_name}': {e}",
        )
        NLP_MODEL = None
        return False


# --- Feature Extraction Functions ---
# These now primarily extract data from the Doc object populated by textdescriptives


def _extract_word_count(doc: spacy.tokens.Doc | None) -> int | None:
    """Extracts word count from textdescriptives stats (token count)."""
    if not doc:
        return None
    try:
        # textdescriptives uses 'n_tokens' within 'descriptive_stats', let's verify this
        # Based on docs, it seems 'counts' includes 'n_tokens'
        token_count = doc._.counts["n_tokens"]
        return int(token_count) if token_count is not None else None
    except (AttributeError, KeyError):
        logger.warning("Could not extract word count (n_tokens) from textdescriptives.")
        # Fallback or alternative: calculate manually?
        # return len([token for token in doc if token.is_alpha])
        return None


def _extract_avg_word_length(doc: spacy.tokens.Doc | None) -> float | None:
    """Extracts average word length from textdescriptives stats."""
    if not doc:
        return None
    try:
        # Uses 'token_length' -> 'mean'
        mean_len = doc._.token_length["mean"]
        return round(mean_len, 2) if mean_len is not None else None
    except (AttributeError, KeyError):
        logger.warning(
            "Could not extract avg word length (token_length.mean) from textdescriptives.",
        )
        return None


def _calculate_noun_to_verb_ratio(doc: spacy.tokens.Doc | None) -> float | None:
    """Calculates the ratio of nouns to verbs using spaCy's POS tags.

    - Returns float('inf') if nouns > 0 and verbs == 0.
    - Returns 0.0 if nouns == 0 and verbs > 0.
    - Returns None if nouns == 0 and verbs == 0.
    - Returns None if the input doc is None or on processing error.
    """
    if not doc:
        return None

    try:
        nouns = len([token for token in doc if token.pos_ == "NOUN"])
        verbs = len([token for token in doc if token.pos_ == "VERB"])

        if verbs == 0:
            if nouns > 0:
                return float("inf")
            return None
        ratio = nouns / verbs
        return round(ratio, 2)
    except Exception as e:
        logger.warning(f"Could not calculate noun_to_verb_ratio: {e}")
        return None


def _extract_readability_flesch_kincaid_grade(
    doc: spacy.tokens.Doc | None,
) -> float | None:
    """Extracts Flesch-Kincaid grade from textdescriptives readability stats."""
    if not doc:
        return None
    try:
        # Uses 'readability' -> 'flesch_kincaid_grade'
        score = doc._.readability["flesch_kincaid_grade"]
        return round(score, 2) if score is not None else None
    except (AttributeError, KeyError):
        logger.warning(
            "Flesch-Kincaid grade attribute not found in doc._.readability. "
            "Is 'textdescriptives/readability' pipe added?",
        )
        return None
    except Exception as e:
        logger.warning(f"Could not extract Flesch-Kincaid grade: {e}")
        return None


# Add more extraction functions here if needed for other metrics in config.yml
# e.g., _extract_sentence_length_mean(doc), _extract_dependency_distance_mean(doc) ...


async def compute_and_store_nlp_stats(
    db_handler: DatabaseHandler,
    settings: Settings,
    essays_for_analysis: list[EssayForComparison],
) -> None:
    """Computes specified NLP statistics for essays using spaCy and textdescriptives,
    and stores them in the database.
    """
    if not await _ensure_spacy_model_loaded():
        logger.error(
            "Halting NLP statistics computation due to spaCy model loading failure.",
        )
        return

    if NLP_MODEL is None:
        logger.error("NLP_MODEL is not loaded. Cannot compute NLP stats.")
        return

    # Map feature names in config to extraction functions
    feature_extractors = {
        "word_count": _extract_word_count,
        "avg_word_length": _extract_avg_word_length,
        "noun_to_verb_ratio": _calculate_noun_to_verb_ratio,  # Manual calculation
        "flesch_kincaid_grade": _extract_readability_flesch_kincaid_grade,
        # Add mappings for other textdescriptives features if requested
        # "sentence_length_mean": lambda d: d._.sentence_length['mean'] if d else None,
    }

    async with db_handler.session() as session:
        for essay_api_model in essays_for_analysis:
            try:
                db_essay = await db_handler.get_essay_by_id(session, essay_api_model.id)
                if not db_essay:
                    logger.warning(
                        f"Essay ID {essay_api_model.id} not found in DB during NLP analysis.",  # noqa: E501
                    )
                    continue

                if not db_essay.processed_content:
                    logger.warning(
                        f"Essay ID {db_essay.id} has no processed text content. "
                        "Setting nlp_analysis_complete=False with empty features.",
                    )
                    db_essay.nlp_features = {}
                    db_essay.nlp_analysis_complete = False
                    await session.flush()
                    continue

                # Process text with spaCy (includes textdescriptives pipe)
                doc = NLP_MODEL(db_essay.processed_content)

                computed_features: dict[str, Any] = {}

                for feature_name in settings.nlp_features_to_compute:
                    if feature_name == "spelling_errors_count":
                        # Get this from pre-computed metadata
                        if db_essay.processing_metadata and isinstance(
                            db_essay.processing_metadata,
                            dict,
                        ):
                            computed_features["spelling_errors_count"] = (
                                db_essay.processing_metadata.get("spell_errors_count")
                            )
                        else:
                            logger.warning(
                                f"Essay ID {db_essay.id}: 'spell_errors_count' missing.",
                            )
                            computed_features["spelling_errors_count"] = None
                    elif feature_name in feature_extractors:
                        try:
                            computed_features[feature_name] = feature_extractors[
                                feature_name
                            ](doc)
                        except (
                            AttributeError,
                            KeyError,
                            TypeError,
                            ValueError,
                        ) as feature_ex:
                            # Catch specific errors from feature extractors
                            logger.error(
                                f"Feature '{feature_name}' error for essay {db_essay.id}: {feature_ex}",
                            )
                            computed_features[feature_name] = (
                                None  # Mark feature as failed
                            )
                        except Exception as general_feature_ex:
                            # Catch any other unexpected error from a specific extractor
                            logger.exception(
                                f"Unexpected error in feature '{feature_name}' for essay {db_essay.id}: {general_feature_ex}",
                            )
                            computed_features[feature_name] = None
                    else:
                        logger.warning(f"Unknown NLP feature requested: {feature_name}")

                # Store computed features and set complete flag
                db_essay.nlp_features = computed_features
                db_essay.nlp_analysis_complete = True
                await session.flush()
                logger.info(
                    f"Essay ID {db_essay.id}: NLP analysis completed and flag set to True."
                )

            except (AttributeError, KeyError, TypeError, ValueError) as processing_ex:
                # Catch specific errors potentially occurring outside feature extraction loop
                # (e.g., issues with doc creation itself, though less likely with checks)
                logger.error(
                    f"Specific processing error for essay ID {essay_api_model.id}: {processing_ex}",
                    exc_info=True,
                )
                if db_essay:  # Ensure db_essay was fetched before error
                    # Set flag to False to indicate NLP analysis was not completed
                    db_essay.nlp_analysis_complete = False
                    error_meta = db_essay.processing_metadata or {}
                    error_meta["nlp_error"] = str(processing_ex)
                    db_essay.processing_metadata = error_meta
                    # Nested try-except for saving error information
                    try:
                        logger.warning(
                            f"Attempting to save NLP error info and set nlp_analysis_complete=False for essay {db_essay.id}",
                        )
                        await session.flush()
                        logger.info(
                            f"Successfully saved NLP error info and set nlp_analysis_complete=False for essay {db_essay.id}",
                        )
                    except Exception as flush_ex:
                        logger.critical(
                            f"Failed to save NLP error info for essay {db_essay.id} after specific error: {flush_ex}",
                            exc_info=True,
                        )
            except Exception as e:  # General fallback handler for unexpected errors
                logger.exception(
                    f"Unexpected error processing NLP stats for essay ID {essay_api_model.id}: {e}",
                )
                if db_essay:  # Ensure db_essay was fetched before error
                    # Set flag to False to indicate NLP analysis was not completed
                    db_essay.nlp_analysis_complete = False
                    error_meta = db_essay.processing_metadata or {}
                    error_meta["nlp_error"] = f"Unexpected: {e!s}"
                    db_essay.processing_metadata = error_meta
                    # Nested try-except for saving error information
                    try:
                        logger.warning(
                            f"Attempting to save NLP error info and set nlp_analysis_complete=False for essay {db_essay.id} after unexpected error.",
                        )
                        await session.flush()
                        logger.info(
                            f"Successfully saved NLP error info and set nlp_analysis_complete=False for essay {db_essay.id}",
                        )
                    except Exception as flush_ex:
                        logger.critical(
                            f"Failed to save NLP error info for essay {db_essay.id} after unexpected error: {flush_ex}",
                            exc_info=True,
                        )

        # Final commit for the batch after processing all essays
        # Note: Individual essay errors were flushed within the loop
        # This commit finalizes successful updates or error states saved.
        logger.info("Attempting final commit for NLP statistics batch.")
        await session.commit()
        logger.info("NLP statistics computation batch completed and committed.")
