from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import time
from datetime import datetime
from src.utils.logger import LoggerMixin
from src.models.models import SOP, SOPStep
from src.tools.base_tool import BaseTool


class EvaluationDimension(Enum):
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness" 
    EFFICIENCY = "efficiency"
    ROBUSTNESS = "robustness"
    ALIGNMENT = "alignment"


@dataclass
class DimensionScore:
    dimension: EvaluationDimension
    score: float  # 0-10 scale
    weight: float = 1.0
    metrics: Dict[str, Any] = None
    issues: List[str] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
        if self.issues is None:
            self.issues = []


@dataclass
class SOPEvaluationResult:
    sop: SOP
    original_plan: Any
    timestamp: datetime
    overall_score: float
    dimension_scores: Dict[EvaluationDimension, DimensionScore]
    passed_checks: List[str]
    failed_checks: List[str]
    recommendations: List[Tuple[str, str]]  # (recommendation, priority)


class SOPEvaluator(LoggerMixin):
    """
    SOP Evaluation Framework - 5 Dimensions Focused
    """
    
    def __init__(self, available_tools: List[str], name="SOPEvaluator"):
        super().__init__(name)
        self.available_tools = available_tools
        self.dimension_weights = {
            EvaluationDimension.CORRECTNESS: 0.25,
            EvaluationDimension.COMPLETENESS: 0.25,
            EvaluationDimension.EFFICIENCY: 0.15,
            EvaluationDimension.ROBUSTNESS: 0.20,
            EvaluationDimension.ALIGNMENT: 0.15
        }
    
    async def evaluate_sop(self, sop: SOP, original_plan: Any, prompt_used: str = "") -> SOPEvaluationResult:
        """Đánh giá SOP theo 5 chiều"""
        self.info("Starting SOP 5D Evaluation...")
        
        start_time = time.time()
        
        # Đánh giá từng dimension
        evaluation_tasks = [
            self._evaluate_correctness(sop),
            self._evaluate_completeness(sop, original_plan),
            self._evaluate_efficiency(sop),
            self._evaluate_robustness(sop),
            self._evaluate_alignment(sop, prompt_used)
        ]
        
        dimension_results = await asyncio.gather(*evaluation_tasks)
        
        # Tổng hợp kết quả
        dimension_scores = {
            result.dimension: result for result in dimension_results
        }
        
        overall_score = self._calculate_overall_score(dimension_scores)
        passed_checks, failed_checks = self._compile_checks(dimension_scores)
        recommendations = self._generate_recommendations(dimension_scores)
        
        eval_time = time.time() - start_time
        
        self.info(f"Evaluation completed in {eval_time:.2f}s - Score: {overall_score}/10")
        
        return SOPEvaluationResult(
            sop=sop,
            original_plan=original_plan,
            timestamp=datetime.now(),
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            recommendations=recommendations
        )
    
    async def _evaluate_correctness(self, sop: SOP) -> DimensionScore:
        """1. CORRECTNESS: Đánh giá tính đúng đắn format và schema"""
        metrics = {}
        issues = []
        score = 10.0  # Start with perfect score, deduct for issues
        
        # 1.1 JSON Structure Validation
        try:
            # Test serialization to JSON
            sop_json = json.dumps(sop.dict(), indent=2)
            metrics["valid_json"] = True
        except Exception as e:
            metrics["valid_json"] = False
            issues.append(f"Invalid JSON structure: {e}")
            score -= 3.0
        
        # 1.2 Schema Validation
        schema_checks = self._validate_schema(sop)
        metrics.update(schema_checks)
        
        for check_name, check_passed in schema_checks.items():
            if not check_passed:
                score -= 0.5
                issues.append(f"Schema violation: {check_name}")
        
        # 1.3 Field Type Validation
        type_checks = self._validate_field_types(sop)
        metrics.update(type_checks)
        
        for check_name, check_passed in type_checks.items():
            if not check_passed:
                score -= 1.0
                issues.append(f"Type violation: {check_name}")
        
        # 1.4 Required Fields Check
        required_checks = self._validate_required_fields(sop)
        metrics.update(required_checks)
        
        for check_name, check_passed in required_checks.items():
            if not check_passed:
                score -= 2.0
                issues.append(f"Missing required field: {check_name}")
        
        return DimensionScore(
            dimension=EvaluationDimension.CORRECTNESS,
            score=max(0, round(score, 2)),
            metrics=metrics,
            issues=issues
        )
    
    async def _evaluate_completeness(self, sop: SOP, original_plan: Any) -> DimensionScore:
        """2. COMPLETENESS: Đánh giá tính đầy đủ - tất cả step được map"""
        metrics = {}
        issues = []
        score = 10.0
        
        # 2.1 Step Coverage
        plan_step_count = self._count_plan_steps(original_plan)
        sop_step_count = len(sop.steps) if sop.steps else 0
        
        metrics["plan_steps"] = plan_step_count
        metrics["sop_steps"] = sop_step_count
        metrics["coverage_ratio"] = sop_step_count / plan_step_count if plan_step_count > 0 else 0
        
        if sop_step_count < plan_step_count:
            missing_steps = plan_step_count - sop_step_count
            score -= missing_steps * 2.0
            issues.append(f"Missing {missing_steps} steps from original plan")
        
        # 2.2 Field Completeness in Steps
        incomplete_steps = 0
        for i, step in enumerate(sop.steps or []):
            step_completeness = self._check_step_completeness(step)
            if not step_completeness["all_required"]:
                incomplete_steps += 1
                issues.append(f"Step {i+1} missing required fields: {step_completeness['missing_fields']}")
        
        if incomplete_steps > 0:
            score -= incomplete_steps * 1.5
            metrics["incomplete_steps"] = incomplete_steps
        
        # 2.3 Parameter Completeness
        parameter_issues = self._check_parameter_completeness(sop)
        if parameter_issues:
            score -= len(parameter_issues) * 1.0
            issues.extend(parameter_issues)
            metrics["parameter_issues"] = len(parameter_issues)
        
        return DimensionScore(
            dimension=EvaluationDimension.COMPLETENESS,
            score=max(0, round(score, 2)),
            metrics=metrics,
            issues=issues
        )
    
    async def _evaluate_efficiency(self, sop: SOP) -> DimensionScore:
        """3. EFFICIENCY: Đánh giá hiệu quả - không dư thừa, không step vô nghĩa"""
        metrics = {}
        issues = []
        score = 10.0
        
        # 3.1 Step Efficiency Analysis
        efficiency_analysis = self._analyze_step_efficiency(sop)
        metrics.update(efficiency_analysis)
        
        # Deduct for redundant steps
        redundant_count = efficiency_analysis.get("redundant_steps", 0)
        if redundant_count > 0:
            score -= redundant_count * 1.5
            issues.append(f"Found {redundant_count} redundant steps")
        
        # Deduct for meaningless steps
        meaningless_count = efficiency_analysis.get("meaningless_steps", 0)
        if meaningless_count > 0:
            score -= meaningless_count * 2.0
            issues.append(f"Found {meaningless_count} meaningless steps")
        
        # 3.2 Parameter Efficiency
        parameter_efficiency = self._analyze_parameter_efficiency(sop)
        metrics.update(parameter_efficiency)
        
        # Deduct for excessive parameters
        excessive_params = parameter_efficiency.get("excessive_parameters", 0)
        if excessive_params > 0:
            score -= excessive_params * 0.5
            issues.append(f"Found {excessive_params} steps with excessive parameters")
        
        # 3.3 SOP Complexity
        complexity_score = self._calculate_complexity(sop)
        metrics["complexity_score"] = complexity_score
        
        if complexity_score > 7:  # High complexity
            score -= 1.0
            issues.append("SOP complexity is too high")
        
        return DimensionScore(
            dimension=EvaluationDimension.EFFICIENCY,
            score=max(0, round(score, 2)),
            metrics=metrics,
            issues=issues
        )
    
    async def _evaluate_robustness(self, sop: SOP) -> DimensionScore:
        """4. ROBUSTNESS: Đánh giá độ bền - không bịa tool, chịu được thay đổi"""
        metrics = {}
        issues = []
        score = 10.0
        
        # 4.1 Tool Existence Validation
        tool_validation = self._validate_tools_exist(sop)
        metrics.update(tool_validation)
        
        fake_tools = tool_validation.get("fake_tools", [])
        if fake_tools:
            score -= len(fake_tools) * 3.0  # Heavy penalty for fake tools
            issues.append(f"Using non-existent tools: {', '.join(fake_tools)}")
        
        # 4.2 Tool Parameter Compatibility
        param_compatibility = self._check_tool_parameter_compatibility(sop)
        metrics.update(param_compatibility)
        
        incompatible_steps = param_compatibility.get("incompatible_steps", 0)
        if incompatible_steps > 0:
            score -= incompatible_steps * 2.0
            issues.append(f"Found {incompatible_steps} steps with incompatible parameters")
        
        # 4.3 Resilience to Tool Changes
        resilience_score = self._evaluate_resilience(sop)
        metrics["resilience_score"] = resilience_score
        
        if resilience_score < 6.0:
            score -= 2.0
            issues.append("SOP is not resilient to tool changes")
        
        # 4.4 Error Handling in Steps
        error_handling = self._check_error_handling(sop)
        metrics.update(error_handling)
        
        if not error_handling.get("has_preconditions", False):
            score -= 1.0
            issues.append("Missing preconditions for error-prone steps")
        
        return DimensionScore(
            dimension=EvaluationDimension.ROBUSTNESS,
            score=max(0, round(score, 2)),
            metrics=metrics,
            issues=issues
        )
    
    async def _evaluate_alignment(self, sop: SOP, prompt_used: str) -> DimensionScore:
        """5. ALIGNMENT: Đánh giá sự tuân thủ - đúng prompt, đúng format, không vi phạm rule"""
        metrics = {}
        issues = []
        score = 10.0
        
        # 5.1 Prompt Compliance
        prompt_compliance = self._check_prompt_compliance(sop, prompt_used)
        metrics.update(prompt_compliance)
        
        if not prompt_compliance.get("follows_instructions", True):
            score -= 3.0
            issues.append("Does not follow prompt instructions")
        
        # 5.2 Output Format Compliance
        format_compliance = self._check_format_compliance(sop)
        metrics.update(format_compliance)
        
        format_violations = format_compliance.get("format_violations", 0)
        if format_violations > 0:
            score -= format_violations * 1.0
            issues.append(f"Found {format_violations} format violations")
        
        # 5.3 Non-Tool Rule Compliance
        rule_compliance = self._check_rule_compliance(sop)
        metrics.update(rule_compliance)
        
        rule_violations = rule_compliance.get("rule_violations", 0)
        if rule_violations > 0:
            score -= rule_violations * 2.0
            issues.append(f"Found {rule_violations} rule violations")
        
        # 5.4 Instruction Following
        instruction_following = self._check_instruction_following(sop)
        metrics.update(instruction_following)
        
        if not instruction_following.get("follows_basic_rules", True):
            score -= 2.0
            issues.append("Does not follow basic instructions")
        
        return DimensionScore(
            dimension=EvaluationDimension.ALIGNMENT,
            score=max(0, round(score, 2)),
            metrics=metrics,
            issues=issues
        )
    
    # ===== IMPLEMENTATION METHODS =====
    
    def _validate_schema(self, sop: SOP) -> Dict[str, bool]:
        """Validate SOP schema compliance"""
        checks = {}
        
        # Check main structure
        checks["has_steps"] = bool(sop.steps and len(sop.steps) > 0)
        checks["steps_is_list"] = isinstance(sop.steps, list)
        
        # Check step structure
        if sop.steps:
            for i, step in enumerate(sop.steps):
                checks[f"step_{i}_has_number"] = hasattr(step, 'step_number') and step.step_number is not None
                checks[f"step_{i}_has_description"] = bool(getattr(step, 'description', None))
                checks[f"step_{i}_has_action_type"] = bool(getattr(step, 'action_type', None))
        
        return checks
    
    def _validate_field_types(self, sop: SOP) -> Dict[str, bool]:
        """Validate field types"""
        checks = {}
        
        if sop.steps:
            for i, step in enumerate(sop.steps):
                # Check action_type is List[str]
                action_type = getattr(step, 'action_type', None)
                checks[f"step_{i}_action_type_list"] = isinstance(action_type, list)
                if action_type:
                    checks[f"step_{i}_action_type_strings"] = all(isinstance(item, str) for item in action_type)
                
                # Check params is Dict
                params = getattr(step, 'params', {})
                checks[f"step_{i}_params_dict"] = isinstance(params, dict)
                
                # Check step_number is int
                step_number = getattr(step, 'step_number', None)
                checks[f"step_{i}_step_number_int"] = isinstance(step_number, int)
        
        return checks
    
    def _validate_required_fields(self, sop: SOP) -> Dict[str, bool]:
        """Validate required fields are present"""
        checks = {}
        
        checks["has_steps_field"] = hasattr(sop, 'steps')
        
        if sop.steps:
            for i, step in enumerate(sop.steps):
                checks[f"step_{i}_has_step_number"] = hasattr(step, 'step_number') and step.step_number is not None
                checks[f"step_{i}_has_description"] = bool(getattr(step, 'description', None))
                checks[f"step_{i}_has_action_type"] = bool(getattr(step, 'action_type', None))
        
        return checks
    
    def _count_plan_steps(self, plan: Any) -> int:
        """Count steps in original plan"""
        if hasattr(plan, 'steps') and isinstance(plan.steps, list):
            return len(plan.steps)
        elif hasattr(plan, '__dict__') and 'steps' in plan.__dict__:
            return len(plan.steps)
        return 0
    
    def _check_step_completeness(self, step: SOPStep) -> Dict[str, Any]:
        """Check if a step has all required components"""
        required_fields = ['step_number', 'description', 'action_type']
        missing_fields = []
        
        for field in required_fields:
            if not hasattr(step, field) or getattr(step, field) is None:
                missing_fields.append(field)
        
        return {
            "all_required": len(missing_fields) == 0,
            "missing_fields": missing_fields
        }
    
    def _check_parameter_completeness(self, sop: SOP) -> List[str]:
        """Check if steps have necessary parameters for their tools"""
        issues = []
        
        for i, step in enumerate(sop.steps or []):
            action_type = getattr(step, 'action_type', None)
            params = getattr(step, 'params', {})
            
            if action_type and len(action_type) >= 2:
                tool_name = action_type[1]
                # Basic parameter checks based on tool type
                if tool_name == "create_file" and not params.get('filename'):
                    issues.append(f"Step {i+1}: create_file missing 'filename' parameter")
                elif tool_name == "edit_file" and not params.get('filename'):
                    issues.append(f"Step {i+1}: edit_file missing 'filename' parameter")
        
        return issues
    
    def _analyze_step_efficiency(self, sop: SOP) -> Dict[str, Any]:
        """Analyze step efficiency and identify redundancies"""
        analysis = {
            "redundant_steps": 0,
            "meaningless_steps": 0,
            "total_steps": len(sop.steps or [])
        }
        
        step_descriptions = []
        step_actions = []
        
        for step in sop.steps or []:
            desc = getattr(step, 'description', '').lower()
            action = getattr(step, 'action_type', [])
            
            step_descriptions.append(desc)
            if action:
                step_actions.append(tuple(action))
            
            # Check for meaningless steps
            meaningless_indicators = ['test', 'debug', 'nothing', 'empty', 'skip']
            if any(indicator in desc for indicator in meaningless_indicators):
                analysis["meaningless_steps"] += 1
        
        # Check for redundant steps (same action and similar description)
        unique_actions = set(step_actions)
        analysis["redundant_steps"] = len(step_actions) - len(unique_actions)
        
        return analysis
    
    def _analyze_parameter_efficiency(self, sop: SOP) -> Dict[str, Any]:
        """Analyze parameter usage efficiency"""
        analysis = {
            "excessive_parameters": 0,
            "average_params_per_step": 0
        }
        
        total_params = 0
        param_counts = []
        
        for step in sop.steps or []:
            params = getattr(step, 'params', {})
            param_count = len(params)
            param_counts.append(param_count)
            total_params += param_count
            
            # Consider more than 5 parameters as excessive
            if param_count > 5:
                analysis["excessive_parameters"] += 1
        
        if param_counts:
            analysis["average_params_per_step"] = sum(param_counts) / len(param_counts)
        
        return analysis
    
    def _calculate_complexity(self, sop: SOP) -> float:
        """Calculate SOP complexity score"""
        complexity = 0.0
        
        if not sop.steps:
            return 0.0
        
        # Base complexity from step count
        complexity += min(len(sop.steps) * 0.5, 5.0)
        
        # Additional complexity from conditions and preconditions
        for step in sop.steps:
            if getattr(step, 'preconditions', None):
                complexity += len(step.preconditions) * 0.3
            if getattr(step, 'condition', None):
                complexity += 1.0
        
        return min(complexity, 10.0)
    
    def _validate_tools_exist(self, sop: SOP) -> Dict[str, Any]:
        """Validate that all referenced tools actually exist"""
        validation = {
            "fake_tools": [],
            "valid_tools": [],
            "tool_coverage": 0.0
        }
        
        total_tools = 0
        valid_tools = 0
        
        for step in sop.steps or []:
            action_type = getattr(step, 'action_type', None)
            if action_type and len(action_type) >= 2:
                tool_name = action_type[1]
                total_tools += 1
                
                if tool_name in self.available_tools:
                    valid_tools += 1
                    validation["valid_tools"].append(tool_name)
                else:
                    validation["fake_tools"].append(tool_name)
        
        if total_tools > 0:
            validation["tool_coverage"] = valid_tools / total_tools
        
        return validation
    
    def _check_tool_parameter_compatibility(self, sop: SOP) -> Dict[str, Any]:
        """Check if step parameters are compatible with tool requirements"""
        analysis = {
            "incompatible_steps": 0,
            "compatibility_issues": []
        }
        
        for i, step in enumerate(sop.steps or []):
            action_type = getattr(step, 'action_type', None)
            params = getattr(step, 'params', {})
            
            if action_type and len(action_type) >= 2:
                tool_name = action_type[1]
                
                # Basic compatibility checks
                if tool_name == "create_file":
                    if not params.get('filename') or not params.get('content'):
                        analysis["incompatible_steps"] += 1
                        analysis["compatibility_issues"].append(
                            f"Step {i+1}: create_file missing required parameters"
                        )
                elif tool_name == "edit_file":
                    if not params.get('filename'):
                        analysis["incompatible_steps"] += 1
                        analysis["compatibility_issues"].append(
                            f"Step {i+1}: edit_file missing 'filename' parameter"
                        )
        
        return analysis
    
    def _evaluate_resilience(self, sop: SOP) -> float:
        """Evaluate resilience to tool changes"""
        resilience_score = 8.0  # Start with good score
        
        tool_usage = {}
        for step in sop.steps or []:
            action_type = getattr(step, 'action_type', None)
            if action_type and len(action_type) >= 2:
                tool_name = action_type[1]
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
        
        # Penalize over-reliance on single tools
        for tool, count in tool_usage.items():
            if count > 3:  # Using same tool too many times
                resilience_score -= 1.0
        
        # Check for alternative approaches
        has_alternatives = len(set(tool_usage.keys())) > 1
        if not has_alternatives and len(sop.steps or []) > 1:
            resilience_score -= 2.0
        
        return max(0, resilience_score)
    
    def _check_error_handling(self, sop: SOP) -> Dict[str, Any]:
        """Check error handling in SOP"""
        analysis = {
            "has_preconditions": False,
            "has_conditions": False,
            "error_handling_steps": 0
        }
        
        for step in sop.steps or []:
            if getattr(step, 'preconditions', None):
                analysis["has_preconditions"] = True
            if getattr(step, 'condition', None):
                analysis["has_conditions"] = True
            
            # Check for error handling in description
            desc = getattr(step, 'description', '').lower()
            error_keywords = ['error', 'fail', 'check', 'validate', 'verify']
            if any(keyword in desc for keyword in error_keywords):
                analysis["error_handling_steps"] += 1
        
        return analysis
    
    def _check_prompt_compliance(self, sop: SOP, prompt_used: str) -> Dict[str, Any]:
        """Check if SOP follows prompt instructions"""
        compliance = {
            "follows_instructions": True,
            "instruction_violations": []
        }
        
        # Check for basic prompt requirements
        prompt_lower = prompt_used.lower()
        
        if "json" in prompt_lower and not self._is_valid_json_structure(sop):
            compliance["follows_instructions"] = False
            compliance["instruction_violations"].append("Not valid JSON structure")
        
        if "step" in prompt_lower and not sop.steps:
            compliance["follows_instructions"] = False
            compliance["instruction_violations"].append("No steps provided")
        
        return compliance
    
    def _check_format_compliance(self, sop: SOP) -> Dict[str, Any]:
        """Check output format compliance"""
        compliance = {
            "format_violations": 0,
            "format_issues": []
        }
        
        # Check step numbering
        step_numbers = [step.step_number for step in sop.steps or [] if hasattr(step, 'step_number')]
        if step_numbers:
            expected_numbers = list(range(1, len(step_numbers) + 1))
            if step_numbers != expected_numbers:
                compliance["format_violations"] += 1
                compliance["format_issues"].append("Step numbering is not sequential")
        
        # Check action_type format
        for i, step in enumerate(sop.steps or []):
            action_type = getattr(step, 'action_type', None)
            if action_type and (not isinstance(action_type, list) or len(action_type) < 2):
                compliance["format_violations"] += 1
                compliance["format_issues"].append(f"Step {i+1}: Invalid action_type format")
        
        return compliance
    
    def _check_rule_compliance(self, sop: SOP) -> Dict[str, Any]:
        """Check non-tool rule compliance"""
        compliance = {
            "rule_violations": 0,
            "rule_issues": []
        }
        
        # Example rules (customize based on your requirements)
        rules = [
            ("No destructive operations without preconditions", self._check_destructive_operations),
            ("No infinite loops in step logic", self._check_infinite_loops),
            ("Reasonable step limits", self._check_step_limits),
        ]
        
        for rule_name, rule_check in rules:
            if not rule_check(sop):
                compliance["rule_violations"] += 1
                compliance["rule_issues"].append(rule_name)
        
        return compliance
    
    def _check_instruction_following(self, sop: SOP) -> Dict[str, Any]:
        """Check basic instruction following"""
        compliance = {
            "follows_basic_rules": True,
            "basic_issues": []
        }
        
        # Check for reasonable descriptions
        for i, step in enumerate(sop.steps or []):
            desc = getattr(step, 'description', '')
            if len(desc) < 5:  # Too short description
                compliance["follows_basic_rules"] = False
                compliance["basic_issues"].append(f"Step {i+1}: Description too short")
            
            if len(desc) > 500:  # Too long description
                compliance["follows_basic_rules"] = False
                compliance["basic_issues"].append(f"Step {i+1}: Description too long")
        
        return compliance
    
    def _is_valid_json_structure(self, sop: SOP) -> bool:
        """Check if SOP has valid JSON structure"""
        try:
            sop_dict = sop.dict()
            json_str = json.dumps(sop_dict)
            return True
        except:
            return False
    
    def _check_destructive_operations(self, sop: SOP) -> bool:
        """Check if destructive operations have proper safeguards"""
        destructive_tools = ['delete_file', 'remove', 'drop', 'truncate']
        
        for step in sop.steps or []:
            action_type = getattr(step, 'action_type', [])
            if any(tool in action_type for tool in destructive_tools):
                if not getattr(step, 'preconditions', None) and not getattr(step, 'condition', None):
                    return False
        return True
    
    def _check_infinite_loops(self, sop: SOP) -> bool:
        """Check for potential infinite loops"""
        # Basic check - if same action repeats too many times
        action_counts = {}
        for step in sop.steps or []:
            action_type = getattr(step, 'action_type', [])
            if action_type:
                action_key = tuple(action_type)
                action_counts[action_key] = action_counts.get(action_key, 0) + 1
                if action_counts[action_key] > 5:  # Same action repeated too many times
                    return False
        return True
    
    def _check_step_limits(self, sop: SOP) -> bool:
        """Check if step count is reasonable"""
        return len(sop.steps or []) <= 50  # Reasonable limit
    
    def _calculate_overall_score(self, dimension_scores: Dict[EvaluationDimension, DimensionScore]) -> float:
        """Calculate weighted overall score"""
        weighted_sum = sum(
            score.score * self.dimension_weights[dimension]
            for dimension, score in dimension_scores.items()
        )
        return round(weighted_sum, 2)
    
    def _compile_checks(self, dimension_scores: Dict[EvaluationDimension, DimensionScore]) -> Tuple[List[str], List[str]]:
        """Compile passed and failed checks"""
        passed_checks = []
        failed_checks = []
        
        for dimension, score_obj in dimension_scores.items():
            if score_obj.score >= 7.0:
                passed_checks.append(f"{dimension.value}: {score_obj.score}/10")
            else:
                failed_checks.append(f"{dimension.value}: {score_obj.score}/10")
                
            # Add specific issues to failed checks
            failed_checks.extend(score_obj.issues)
        
        return passed_checks, failed_checks
    
    def _generate_recommendations(self, dimension_scores: Dict[EvaluationDimension, DimensionScore]) -> List[Tuple[str, str]]:
        """Generate prioritized recommendations"""
        recommendations = []
        
        for dimension, score_obj in dimension_scores.items():
            if score_obj.score < 7.0 and score_obj.issues:
                # Get the most critical issue
                critical_issue = score_obj.issues[0] if score_obj.issues else "Needs improvement"
                priority = "HIGH" if score_obj.score < 5.0 else "MEDIUM"
                recommendations.append((f"Fix {critical_issue}", priority))
        
        # Limit to top 3 recommendations
        return recommendations[:3]


# ===== USAGE EXAMPLE =====
async def demo_sop_evaluation():
    """Demo SOP evaluation"""
    
    # Get available tools
    available_tools = BaseTool.list_tools()
    
    # Create evaluator
    evaluator = SOPEvaluator(available_tools)
    
    # Example SOP (in practice, you'd use real SOP from your engine)
    example_sop = SOP(
        steps=[
            SOPStep(
                step_number=1,
                description="Create a new file with initial content",
                action_type=["file", "create_file"],
                params={"filename": "test.txt", "content": "Hello World"}
            ),
            SOPStep(
                step_number=2, 
                description="Edit the file to add more content",
                action_type=["file", "edit_file"],
                params={"filename": "test.txt", "new_content": "Additional content", "mode": "append"}
            )
        ],
        final_target="Create and modify a text file"
    )
    
    # Example plan
    class ExamplePlan:
        steps = ["Create file", "Edit file"]
    
    # Run evaluation
    result = await evaluator.evaluate_sop(
        sop=example_sop,
        original_plan=ExamplePlan(),
        prompt_used="Convert plan to SOP JSON"
    )
    
    # Print results
    print(f"\n🎯 SOP 5D EVALUATION RESULTS")
    print(f"Overall Score: {result.overall_score}/10")
    print(f"Timestamp: {result.timestamp}")
    
    print(f"\n📊 DIMENSION SCORES:")
    for dimension, score_obj in result.dimension_scores.items():
        print(f"  {dimension.value.upper()}: {score_obj.score}/10")
        if score_obj.issues:
            print(f"    Issues: {score_obj.issues}")
    
    print(f"\n✅ PASSED CHECKS: {result.passed_checks}")
    print(f"❌ FAILED CHECKS: {result.failed_checks}")
    print(f"🚀 RECOMMENDATIONS: {result.recommendations}")
    
    return result


if __name__ == "__main__":
    asyncio.run(demo_sop_evaluation())