# Claude Code Plugins Usage Guide

Comprehensive guide for using installed Claude Code plugins for AI/ML development, NLP, and frontend testing workflows.

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [How Plugins Work](#how-plugins-work)
- [AI/ML Engineering Pack](#aiml-engineering-pack)
- [NLP Plugins](#nlp-plugins)
- [Testing Plugins](#testing-plugins)
- [Quick Start Examples](#quick-start-examples)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

This project uses plugins from the **jeremylongshore/claude-code-plugins-plus** marketplace, providing:
- **229 production-ready plugins** across 12 categories
- **Automatic activation** based on conversation context
- **Integration** with project workflows and tools

**Installed Plugin Categories:**
- AI/ML Engineering (12-plugin bundle)
- NLP & Text Analysis
- Frontend Testing & Accessibility
- Visual Regression & Browser Testing

---

## Installation

### Add Marketplace
```bash
/plugin marketplace add jeremylongshore/claude-code-plugins-plus
```

### Install Plugins

**AI/ML Bundle:**
```bash
/plugin install ai-ml-engineering-pack@claude-code-plugins-plus
```

**NLP Tools:**
```bash
/plugin install nlp-text-analyzer@claude-code-plugins-plus
/plugin install sentiment-analysis-tool@claude-code-plugins-plus
```

**Testing Tools:**
```bash
/plugin install e2e-test-framework@claude-code-plugins-plus
/plugin install browser-compatibility-tester@claude-code-plugins-plus
/plugin install visual-regression-tester@claude-code-plugins-plus
/plugin install accessibility-test-scanner@claude-code-plugins-plus
/plugin install test-doubles-generator@claude-code-plugins-plus
/plugin install snapshot-test-manager@claude-code-plugins-plus
```

**After installation:** Restart Claude Code to activate plugins.

### Verify Installation
```bash
/plugin list
```

---

## How Plugins Work

Plugins activate through **three mechanisms**:

### 1. Agent Skills (Automatic) - Primary Method

Plugins activate automatically based on natural language context.

**Example:**
```
You: "I need to build a neural network for image classification"
→ Claude automatically activates: neural-network-builder skill
```

**No special commands needed** - just describe your task naturally.

### 2. Slash Commands (Explicit)

Some plugins provide specific commands:

| Command | Plugin | Purpose |
|---------|--------|---------|
| `/gut` | Unit Test Generator | Generate unit tests |
| `/e2e` | E2E Test Framework | Run E2E tests |
| `/cov` | Test Coverage Analyzer | Analyze code coverage |
| `/reg` | Regression Test Tracker | Manage regression tests |

### 3. Subagents (Context-Based)

Specialized agents that activate during specific workflows automatically.

---

## AI/ML Engineering Pack

**Bundle includes 12 expert plugins** for professional AI/ML development.

### Capabilities

- **Prompt Engineering** - Template creation, few-shot learning
- **LLM Integration** - OpenAI, Anthropic, Google AI integration patterns
- **RAG Systems** - Retrieval-Augmented Generation setup
- **Vector Databases** - Pinecone, Weaviate, ChromaDB configuration
- **AI Safety** - Bias detection, fairness validation
- **Cost Optimization** - Token usage optimization, caching strategies
- **Model Deployment** - Production-ready deployment patterns

### Usage Examples

**RAG System Setup:**
```
"Set up a RAG system using Pinecone and OpenAI embeddings for document search"
```

**LLM Integration:**
```
"Create a FastAPI endpoint that uses Claude with streaming responses"
```

**Prompt Engineering:**
```
"Build a few-shot learning prompt template for classification tasks"
```

**Cost Optimization:**
```
"Optimize my LLM API costs by implementing caching and batching"
```

**Model Deployment:**
```
"Deploy my PyTorch model as a production-ready API with monitoring"
```

### Individual ML Plugins

| Plugin | Use Case | Example Command |
|--------|----------|-----------------|
| **neural-network-builder** | Build neural architectures | "Build a CNN for image classification with PyTorch" |
| **ml-model-trainer** | Train ML models | "Train a random forest model on this customer dataset" |
| **hyperparameter-tuner** | Optimize parameters | "Tune hyperparameters using Bayesian optimization" |
| **feature-engineering-toolkit** | Create features | "Generate polynomial and interaction features" |
| **data-preprocessing-pipeline** | Clean data | "Preprocess dataset: handle nulls, scale, encode categoricals" |
| **model-deployment-helper** | Deploy models | "Deploy my model as a FastAPI endpoint with Docker" |
| **experiment-tracking-setup** | Track experiments | "Set up MLflow for experiment tracking and model registry" |
| **automl-pipeline-builder** | AutoML | "Build an AutoML pipeline with auto-sklearn" |
| **model-evaluation-suite** | Evaluate models | "Generate comprehensive evaluation metrics and reports" |
| **ai-ethics-validator** | Validate fairness | "Check my model for bias across demographic groups" |

---

## NLP Plugins

### nlp-text-analyzer

**Capabilities:**
- Tokenization and text preprocessing
- Named Entity Recognition (NER)
- Part-of-Speech (POS) tagging
- Keyword extraction
- Text complexity analysis

**Usage Examples:**

```
"Tokenize this text and extract named entities"
"Perform POS tagging on customer feedback data"
"Extract keywords from product reviews"
"Analyze readability scores for educational content"
"Preprocess text for machine learning: lowercase, remove stopwords, lemmatize"
```

### sentiment-analysis-tool

**Capabilities:**
- Sentiment classification (positive/negative/neutral)
- Emotion detection
- Opinion mining
- Multi-language support

**Usage Examples:**

```
"Analyze sentiment of customer reviews in this CSV file"
"Classify support tickets by emotional tone"
"Extract positive and negative opinions from survey responses"
"Build a sentiment analysis dashboard for social media monitoring"
```

### Integration with HuleEdu

**Educational Assessment:**
```
"Analyze student essay sentiment and emotional engagement"
"Extract key topics from student writing samples"
"Evaluate text complexity for grade-level appropriateness"
```

**Feedback Analysis:**
```
"Analyze teacher feedback sentiment across classes"
"Extract common themes from parent-teacher communication"
```

---

## Testing Plugins

### E2E Test Framework

**Supported Frameworks:** Playwright, Cypress, Selenium

**Usage Examples:**

```
"Create Playwright tests for the student login flow"
"Set up Cypress tests for the essay submission process"
"Generate E2E tests for the teacher dashboard navigation"
"Test the assignment creation workflow across multiple browsers"
```

**Project-Specific:**
```
"Create E2E tests for the Svelte frontend components"
"Test WebSocket connections in the assessment service"
```

### Visual Regression Tester

**Supported Tools:** Percy, Chromatic, BackstopJS

**Usage Examples:**

```
"Set up visual regression testing with Percy for the component library"
"Create visual diff tests for the student dashboard UI"
"Configure BackstopJS to test responsive layouts"
"Detect unintended UI changes in the assessment interface"
```

### Browser Compatibility Tester

**Supported Tools:** BrowserStack, Selenium Grid, Playwright

**Usage Examples:**

```
"Test the student portal across Chrome, Firefox, and Safari"
"Set up cross-browser testing with BrowserStack"
"Create Selenium Grid tests for legacy browser support"
"Verify the essay editor works on mobile browsers"
```

### Accessibility Test Scanner

**Standards:** WCAG 2.1 AA/AAA, Section 508

**Usage Examples:**

```
"Scan the student dashboard for WCAG 2.1 AA compliance"
"Test screen reader compatibility for the assignment interface"
"Check keyboard navigation in the essay editor"
"Validate form accessibility for student registration"
"Generate accessibility report for the teacher portal"
```

### Test Doubles Generator

**Supported Libraries:** Jest, Sinon, Vitest

**Usage Examples:**

```
"Create Jest mocks for the API gateway client"
"Generate Sinon stubs for Kafka producer in tests"
"Mock the authentication service for integration tests"
"Create test doubles for the file upload service"
```

### Snapshot Test Manager

**Usage Examples:**

```
"Update all snapshots in the Svelte component tests"
"Analyze snapshot test diffs for the UI library"
"Generate snapshots for newly created React components"
"Review and approve snapshot changes after refactoring"
```

### Unit Test Generator

**Command:** `/gut`

**Usage Examples:**

```
"Generate unit tests for the essay grading service"
"/gut for the batch processing logic"
"Create comprehensive unit tests with edge cases for the consensus model"
```

### Test Coverage Analyzer

**Command:** `/cov`

**Usage Examples:**

```
"/cov for the class management service"
"Analyze test coverage and identify gaps in the assessment service"
"Generate coverage report for the frontend components"
```

---

## Quick Start Examples

### Example 1: ML Model Development Workflow

**Task:** Build a student performance prediction model

```
You: "I have student assessment data in CSV format. I want to build a model
     to predict student performance. Walk me through data preprocessing,
     feature engineering, model training, evaluation, and deployment."

Activated plugins:
✓ data-preprocessing-pipeline - Clean and validate data
✓ feature-engineering-toolkit - Create predictive features
✓ ml-model-trainer - Train classification model
✓ hyperparameter-tuner - Optimize model parameters
✓ model-evaluation-suite - Generate evaluation metrics
✓ ai-ethics-validator - Check for bias across demographics
✓ model-deployment-helper - Deploy as FastAPI endpoint
```

### Example 2: NLP Pipeline for Essay Analysis

**Task:** Analyze student essays for sentiment and topics

```
You: "Analyze sentiment and extract key topics from student essays.
     I want to identify emotional engagement and main themes."

Activated plugins:
✓ nlp-text-analyzer - Tokenization, NER, keyword extraction
✓ sentiment-analysis-tool - Sentiment scoring and emotion detection
✓ data-visualization-creator - Create visualizations
```

### Example 3: Comprehensive Test Suite Setup

**Task:** Set up testing for Svelte frontend

```
You: "Set up comprehensive testing for the Svelte student dashboard:
     unit tests for components, E2E tests for workflows,
     accessibility checks, and visual regression testing."

Activated plugins:
✓ Unit Test Generator - Vitest tests for components
✓ e2e-test-framework - Playwright E2E tests
✓ accessibility-test-scanner - WCAG compliance
✓ visual-regression-tester - UI regression tests
✓ browser-compatibility-tester - Cross-browser testing
```

### Example 4: RAG System for Educational Content

**Task:** Build semantic search for educational materials

```
You: "Build a RAG system for semantic search of educational materials.
     Use Pinecone for vector storage and OpenAI embeddings.
     Deploy as a FastAPI endpoint."

Activated plugins:
✓ AI/ML Engineering Pack - RAG architecture, vector DB setup
✓ model-deployment-helper - FastAPI deployment
✓ experiment-tracking-setup - Track embedding experiments
```

---

## Best Practices

### For ML/NLP Work

1. **Be specific about your tech stack:**
   ```
   Good: "Train a PyTorch model with GPU acceleration and mixed precision"
   Bad:  "Train a model"
   ```

2. **Mention data characteristics:**
   ```
   "I have 50K labeled examples with class imbalance (90/10 split)"
   ```

3. **Request end-to-end workflows:**
   ```
   "Take me from raw CSV to deployed model with monitoring"
   ```

4. **Specify deployment requirements:**
   ```
   "Deploy to Docker with FastAPI, include health checks and logging"
   ```

### For Testing

1. **Describe testing goals clearly:**
   ```
   "Test the essay submission flow: unit tests, E2E tests, accessibility"
   ```

2. **Specify frameworks and standards:**
   ```
   "Use Playwright for E2E tests, ensure WCAG 2.1 AA compliance"
   ```

3. **Mention CI/CD integration:**
   ```
   "Generate tests that run in GitHub Actions with coverage reporting"
   ```

### For HuleEdu Project

1. **Reference project architecture:**
   ```
   "Create tests for the Quart-based assessment service using our DI patterns"
   ```

2. **Follow project conventions:**
   ```
   "Use our standard test structure: no conftest, explicit utils imports"
   ```

3. **Integrate with observability:**
   ```
   "Include structured logging using our centralized error handling"
   ```

---

## Troubleshooting

### Plugin Not Activating

**Check installation:**
```bash
/plugin list
```

**Restart Claude Code:**
Plugins require restart to activate.

**Be more specific:**
```
Instead of: "Help with testing"
Try:        "Create Playwright E2E tests for the login flow"
```

### Wrong Plugin Activating

**Mention specific tools:**
```
"Use Playwright specifically for E2E testing"
"I want to use Cypress, not Selenium"
```

### Plugin Conflicts

**Disable unused plugins:**
```bash
/plugin uninstall plugin-name@marketplace-name
```

### Getting Help

**Ask about plugin capabilities:**
```
"What can the neural-network-builder plugin do?"
"Show examples of using the accessibility-test-scanner"
"What are the best practices for the hyperparameter-tuner?"
```

**Check marketplace documentation:**
```
https://claudecodeplugins.io
https://github.com/jeremylongshore/claude-code-plugins-plus
```

---

## Additional Resources

### Marketplace
- **Homepage:** https://claudecodeplugins.io
- **GitHub:** https://github.com/jeremylongshore/claude-code-plugins-plus
- **License:** MIT (100% open source)

### Plugin Categories
- **DevOps** (25 plugins) - CI/CD, deployment, monitoring
- **Security** (20 plugins) - OWASP scanning, penetration testing
- **Database** (15 plugins) - Migration, optimization, backup
- **AI/ML** (27 plugins) - Model development, NLP, computer vision
- **Testing** (25 plugins) - Unit, integration, E2E, performance
- **API Development** - REST, GraphQL, OpenAPI

### Related Documentation
- [CLAUDE.md](../CLAUDE.md) - Project development workflow
- [Test Creation Methodology](.cursor/rules/075-test-creation-methodology.md)
- [Architectural Mandates](.cursor/rules/020-architectural-mandates.md)

---

**Last Updated:** 2025-10-31
**Marketplace Version:** claude-code-plugins-plus v1.0.0
**Total Plugins Installed:** 10
