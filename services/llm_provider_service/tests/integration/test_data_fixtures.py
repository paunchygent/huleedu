"""Test data fixtures for LLM provider integration tests.

This module contains representative prompts and essays used across integration tests
to validate model compatibility with CJ assessment workflows.
"""

from __future__ import annotations

# Representative essays for CJ assessment testing
# These simulate the quality difference between strong and weak student essays

ESSAY_A_STRONG = """Climate change represents one of the most pressing challenges facing humanity today.
The scientific consensus is clear: human activities, particularly the burning of fossil
fuels, are driving unprecedented changes in our planet's climate. The evidence is
overwhelming, from rising global temperatures to melting polar ice caps and increasingly
severe weather events. This essay examines the causes, impacts, and potential solutions
to this critical issue.

First, the primary cause of climate change is the emission of greenhouse gases,
particularly carbon dioxide and methane. These gases trap heat in Earth's atmosphere,
creating a warming effect that disrupts natural climate patterns. The industrial
revolution marked the beginning of large-scale fossil fuel combustion, and emissions
have accelerated dramatically in recent decades. Data from ice cores and atmospheric
measurements show CO2 levels have reached their highest point in at least 800,000 years.

Second, the impacts of climate change are already being felt worldwide. Rising sea
levels threaten coastal communities and small island nations. Changes in precipitation
patterns affect agriculture and water security. Extreme weather events, including
hurricanes, droughts, and heat waves, are becoming more frequent and severe.
Ecosystems are being disrupted, with species facing extinction as their habitats change
faster than they can adapt.

Finally, addressing climate change requires coordinated global action across multiple
fronts. Transitioning to renewable energy sources like solar and wind power is essential.
Improving energy efficiency in buildings, transportation, and industry can significantly
reduce emissions. Protecting and restoring forests and other carbon sinks helps absorb
CO2 from the atmosphere. International cooperation through agreements like the Paris
Accord provides a framework for collective action.

In conclusion, climate change poses an existential threat that demands immediate and
sustained action. While the challenge is daunting, solutions exist if we have the
political will to implement them. The future of our planet depends on the choices we
make today."""

ESSAY_B_WEAK = """Climate change is a big problem that affects everyone. Many people are worried about
it and think we should do something. There are different opinions about what causes
it and what we should do about it.

Some people say that humans are causing climate change by burning fossil fuels and
cutting down forests. Other people think that climate change is natural and has
happened before in Earth's history. There is a lot of debate about this topic.

The weather is changing in many places. Some places are getting hotter and some are
getting colder. There are also more storms and other extreme weather events. This
affects people's lives and the environment.

We should probably try to reduce pollution and use cleaner energy sources. Things
like solar panels and wind turbines could help. Recycling is also important. If
everyone does their part, maybe we can make a difference.

Climate change is complicated and there is still a lot we don't know about it.
Scientists are studying it to learn more. Hopefully they will find better solutions
in the future."""

# Simplified essays for quick tests
SHORT_ESSAY_A = "This is a well-structured essay with clear thesis and evidence."
SHORT_ESSAY_B = "This essay lacks organization and has weak arguments."

# Representative prompt for full integration tests
REPRESENTATIVE_COMPARISON_PROMPT = """Compare these two essays and determine which is better written based on clarity, structure, argument quality, and writing mechanics."""
