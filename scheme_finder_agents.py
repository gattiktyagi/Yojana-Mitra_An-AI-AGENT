"""
Government Scheme Finder - Multi-Agent System
Uses Gemini API for AI-powered scheme discovery and application assistance
"""

import json
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

try:
    import google.generativeai as genai
except ImportError:
    print("Please install google-generativeai: pip install google-generativeai")
    exit(1)


class AgentType(Enum):
    """Types of agents in the system"""
    ELIGIBILITY_MATCHER = "eligibility_matcher"
    SIMPLIFIER = "simplifier"
    APPLICATION_GUIDE = "application_guide"
    QUERY_RESOLVER = "query_resolver"


@dataclass
class UserProfile:
    """User profile for eligibility matching"""
    age: int
    income: Optional[float]
    location_type: str  # "urban" or "rural"
    occupation: str
    gender: str
    has_bank_account: bool
    caste_category: Optional[str]  # "SC", "ST", "OBC", "General"
    family_size: int
    owns_house: bool
    land_ownership: Optional[float]  # in acres
    education_level: str
    has_disability: bool
    additional_info: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert profile to dictionary"""
        return {
            "age": self.age,
            "income": self.income,
            "location_type": self.location_type,
            "occupation": self.occupation,
            "gender": self.gender,
            "has_bank_account": self.has_bank_account,
            "caste_category": self.caste_category,
            "family_size": self.family_size,
            "owns_house": self.owns_house,
            "land_ownership": self.land_ownership,
            "education_level": self.education_level,
            "has_disability": self.has_disability,
            "additional_info": self.additional_info
        }


class BaseAgent:
    """Base class for all agents"""
    
    def __init__(self, api_key: str, agent_type: AgentType):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('models/gemini-3.1-flash-lite')
        self.agent_type = agent_type
        self.chat = None
    
    def _create_system_prompt(self) -> str:
        """Override this in child classes"""
        raise NotImplementedError
    
    def process(self, input_data: Any) -> str:
        """Process input and return response"""
        raise NotImplementedError


class EligibilityMatcherAgent(BaseAgent):
    """Agent that matches users with eligible schemes"""
    
    def __init__(self, api_key: str, schemes_data: List[Dict]):
        super().__init__(api_key, AgentType.ELIGIBILITY_MATCHER)
        self.schemes_data = schemes_data
    
    def _create_system_prompt(self) -> str:
        return """You are an expert eligibility matcher for Indian government schemes.
Your job is to analyze user profiles and match them with eligible schemes based on:
- Age criteria
- Income limits
- Location (urban/rural)
- Occupation
- Gender
- Caste category
- Asset ownership
- Family composition

Provide a JSON response with:
1. matched_schemes: List of scheme IDs that the user is eligible for
2. reasoning: Brief explanation for each match
3. confidence_score: 0-100 for each match

Be thorough and inclusive - if criteria are borderline, include the scheme with a note."""

    def _parse_eligibility_criteria(self, scheme: Dict, user_profile: UserProfile) -> Dict[str, Any]:
        """Parse and check eligibility criteria - ULTRA STRICT VERSION"""
        eligible = True
        reasons = []
        
        # Get all scheme text for analysis
        scheme_name_lower = scheme.get('scheme_name', '').lower()
        scheme_category = scheme.get('category', '').lower()
        eligibility_text = scheme.get('eligibility', '').lower()
        target_beneficiaries = scheme.get('target_beneficiaries', '').lower()
        scheme_type = scheme.get('scheme_type', '').lower()
        
        # Combine all text for comprehensive checking
        all_scheme_text = f"{scheme_name_lower} {scheme_category} {eligibility_text} {target_beneficiaries} {scheme_type}"
        
        # Define strict occupation categories
        farmer_keywords = ['farmer', 'agriculture', 'crop', 'kisan', 'krishi', 'fasal', 'sinchai', 
                          'irrigation', 'farm', 'agricultural', 'agri', 'cultivation', 'pesticide']
        
        student_keywords = ['student', 'education', 'scholarship', 'school', 'college', 'study', 
                           'vidya', 'merit', 'academic', 'university', 'campus', 'learning']
        
        business_keywords = ['business', 'entrepreneur', 'mudra', 'msme', 'startup', 'enterprise',
                            'vyapar', 'udyog', 'industry', 'commercial', 'trade']
        
        worker_keywords = ['worker', 'labour', 'labor', 'shram', 'mazdoor', 'employee', 'wage',
                          'construction', 'unorganized']
        
        women_keywords = ['women', 'woman', 'mahila', 'girl', 'daughter', 'beti', 'female',
                         'maternity', 'mother', 'widow']
        
        child_keywords = ['child', 'children', 'infant', 'baby', 'newborn', 'kid', 'balak',
                         'bachcha', 'minor']
        
        elderly_keywords = ['pension', 'senior', 'elderly', 'old age', 'aged', 'vridha',
                           'retirement', 'retired']
        
        health_keywords = ['health', 'medical', 'hospital', 'insurance', 'treatment', 'arogya',
                          'swasthya', 'clinic', 'doctor']
        
        housing_keywords = ['house', 'housing', 'awas', 'home', 'shelter', 'construction',
                           'building', 'residence', 'dwelling']
        
        livestock_keywords = ['livestock', 'dairy', 'cattle', 'gokul', 'pashu', 'animal husbandry',
                             'cow', 'buffalo', 'goat', 'sheep', 'poultry']
        
        fishery_keywords = ['fish', 'fishery', 'fisheries', 'matsya', 'aqua', 'fisher', 'fishing',
                           'marine', 'aquaculture']
        
        skill_keywords = ['skill', 'training', 'kaushal', 'vocational', 'apprentice', 'coaching']
        
        # Get user info
        user_occ = user_profile.occupation.lower()
        user_age = user_profile.age
        user_gender = user_profile.gender.lower()
        
        # === STRICT OCCUPATION FILTERING ===
        
        # Check if scheme is occupation-specific
        is_farmer_scheme = any(kw in all_scheme_text for kw in farmer_keywords)
        is_student_scheme = any(kw in all_scheme_text for kw in student_keywords)
        is_business_scheme = any(kw in all_scheme_text for kw in business_keywords)
        is_worker_scheme = any(kw in all_scheme_text for kw in worker_keywords)
        is_livestock_scheme = any(kw in all_scheme_text for kw in livestock_keywords)
        is_fishery_scheme = any(kw in all_scheme_text for kw in fishery_keywords)
        is_skill_scheme = any(kw in all_scheme_text for kw in skill_keywords)
        
        # ULTRA STRICT: If scheme is for specific occupation, user MUST have that occupation
        if is_farmer_scheme:
            user_is_farmer = any(kw in user_occ for kw in ['farmer', 'agriculture', 'krishi', 'kisan', 'farm'])
            if not user_is_farmer:
                return {'eligible': False, 'reasons': ['Exclusively for farmers'], 'confidence': 0}
        
        if is_student_scheme:
            user_is_student = any(kw in user_occ for kw in ['student', 'studying', 'school', 'college', 'education'])
            if not user_is_student:
                return {'eligible': False, 'reasons': ['Exclusively for students'], 'confidence': 0}
        
        if is_business_scheme:
            user_is_business = any(kw in user_occ for kw in ['business', 'entrepreneur', 'owner', 'trader', 'self-employed', 'vyapari'])
            if not user_is_business:
                return {'eligible': False, 'reasons': ['Exclusively for business owners'], 'confidence': 0}
        
        if is_worker_scheme:
            user_is_worker = any(kw in user_occ for kw in ['worker', 'labour', 'labor', 'employee', 'mazdoor', 'daily wage'])
            if not user_is_worker:
                return {'eligible': False, 'reasons': ['Exclusively for workers/laborers'], 'confidence': 0}
        
        if is_livestock_scheme:
            user_has_livestock = any(kw in user_occ for kw in ['dairy', 'livestock', 'cattle', 'farmer']) or \
                                user_profile.additional_info.get('has_livestock', False)
            if not user_has_livestock:
                return {'eligible': False, 'reasons': ['Exclusively for livestock farmers'], 'confidence': 0}
        
        if is_fishery_scheme:
            user_is_fisher = any(kw in user_occ for kw in ['fisher', 'fish', 'aqua', 'marine'])
            if not user_is_fisher:
                return {'eligible': False, 'reasons': ['Exclusively for fishermen'], 'confidence': 0}
        
        # === STRICT AGE FILTERING ===
        age_limit = scheme.get('age_limit', 'No limit')
        if age_limit != 'No limit':
            try:
                if '–' in age_limit or '-' in age_limit:
                    parts = age_limit.replace('–', '-').split('-')
                    
                    # Parse minimum age
                    min_age_str = parts[0].strip()
                    if 'month' in min_age_str.lower():
                        min_age = 0
                    elif 'year' in min_age_str.lower():
                        min_age = int(''.join(filter(str.isdigit, min_age_str)))
                    else:
                        min_age = int(min_age_str)
                    
                    # Parse maximum age
                    if len(parts) > 1:
                        max_age_str = parts[1].strip()
                        if 'month' in max_age_str.lower():
                            max_age = 1  # Less than 1 year
                        elif 'year' in max_age_str.lower():
                            max_age = int(''.join(filter(str.isdigit, max_age_str)))
                        else:
                            max_age = int(max_age_str)
                    else:
                        max_age = 150
                    
                    # STRICT: Must be within range
                    if not (min_age <= user_age <= max_age):
                        return {'eligible': False, 'reasons': [f'Age must be {age_limit}'], 'confidence': 0}
                        
                elif '+' in age_limit:
                    min_age_str = age_limit.replace('+', '').strip()
                    if 'month' in min_age_str.lower():
                        min_age = 0
                    elif 'year' in min_age_str.lower():
                        min_age = int(''.join(filter(str.isdigit, min_age_str)))
                    else:
                        min_age = int(min_age_str)
                    
                    if user_age < min_age:
                        return {'eligible': False, 'reasons': [f'Minimum age is {min_age}'], 'confidence': 0}
            except (ValueError, IndexError):
                # If unclear, include with note
                reasons.append(f"Age criteria needs verification: {age_limit}")
        
        # === STRICT GENDER FILTERING ===
        is_women_scheme = any(kw in all_scheme_text for kw in women_keywords)
        if is_women_scheme:
            if user_gender not in ['female', 'f', 'woman']:
                return {'eligible': False, 'reasons': ['Exclusively for women'], 'confidence': 0}
        
        # === STRICT LOCATION FILTERING ===
        is_rural_scheme = 'rural' in all_scheme_text or 'gramin' in all_scheme_text or 'village' in all_scheme_text
        is_urban_scheme = 'urban' in all_scheme_text and 'rural' not in all_scheme_text
        
        if is_rural_scheme and not is_urban_scheme:
            if user_profile.location_type != 'rural':
                return {'eligible': False, 'reasons': ['Exclusively for rural areas'], 'confidence': 0}
        
        if is_urban_scheme and not is_rural_scheme:
            if user_profile.location_type != 'urban':
                return {'eligible': False, 'reasons': ['Exclusively for urban areas'], 'confidence': 0}
        
        # === STRICT INCOME FILTERING ===
        income_limit = scheme.get('income_limit', 'No limit')
        if income_limit not in ['No limit', 'As per SECC data', 'BPL households', 'Excludes institutional landholders', 'BPL / SECC-based']:
            if user_profile.income:
                try:
                    if '₹' in income_limit and 'lakh' in income_limit.lower():
                        numbers = re.findall(r'\d+', income_limit)
                        if numbers:
                            max_income_lakhs = int(numbers[-1])
                            if user_profile.income > max_income_lakhs * 100000:
                                return {'eligible': False, 'reasons': [f'Income exceeds ₹{max_income_lakhs} lakh limit'], 'confidence': 0}
                except (ValueError, IndexError):
                    pass
        
        # === CONTEXTUAL FILTERING ===
        
        # Skill/Training schemes - prefer unemployed or young
        if is_skill_scheme:
            if user_age > 45:
                reasons.append("Primarily for younger individuals")
                eligible = False  # STRICT: Don't show to older people
                return {'eligible': False, 'reasons': reasons, 'confidence': 0}
            if 'employed' in user_occ and 'unemployed' not in user_occ:
                reasons.append("Primarily for unemployed youth")
        
        # Pension schemes - only for people near retirement age
        is_pension_scheme = any(kw in all_scheme_text for kw in elderly_keywords)
        if is_pension_scheme:
            if user_age < 40:
                return {'eligible': False, 'reasons': ['Pension schemes are for people 40+'], 'confidence': 0}
        
        # Child schemes - only if user has children or is very young
        is_child_scheme = any(kw in all_scheme_text for kw in child_keywords)
        if is_child_scheme:
            if user_age > 10 and not user_profile.additional_info.get('has_children', False):
                return {'eligible': False, 'reasons': ['For children or parents with children'], 'confidence': 0}
        
        # === CONFIDENCE SCORING ===
        # Only schemes that passed all filters reach here
        
        if not reasons:
            confidence = 95  # Perfect match
        elif len(reasons) == 1:
            confidence = 75  # One note
        else:
            confidence = 60  # Multiple notes
        
        return {
            'eligible': eligible,
            'reasons': reasons,
            'confidence': confidence
        }
    
    def process(self, user_profile: UserProfile) -> Dict[str, Any]:
        """Match user with eligible schemes - with AI verification for accuracy"""
        
        # First pass: rule-based filtering
        eligible_schemes = []
        
        for scheme in self.schemes_data:
            eligibility_check = self._parse_eligibility_criteria(scheme, user_profile)
            
            # Include schemes with confidence >= 60
            if eligibility_check['eligible'] and eligibility_check['confidence'] >= 60:
                eligible_schemes.append({
                    'scheme_id': scheme['scheme_id'],
                    'scheme_name': scheme['scheme_name'],
                    'scheme_type': scheme['scheme_type'],
                    'category': scheme.get('category', ''),
                    'domain': scheme.get('domain', 'सामान्य (General)'),
                    'benefits': scheme['benefits'],
                    'confidence': eligibility_check['confidence'],
                    'notes': eligibility_check['reasons'],
                    'eligibility': scheme.get('eligibility', ''),
                    'target_beneficiaries': scheme.get('target_beneficiaries', '')
                })
        
        # Sort by confidence (highest first)
        eligible_schemes.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Second pass: AI verification for top candidates (if >10 schemes found)
        if len(eligible_schemes) > 10:
            eligible_schemes = self._ai_verify_top_schemes(eligible_schemes[:25], user_profile)
        
        return {
            'total_matched': len(eligible_schemes),
            'matched_schemes': eligible_schemes,
            'user_profile_summary': user_profile.to_dict()
        }
    
    def _ai_verify_top_schemes(self, schemes: List[Dict], user_profile: UserProfile) -> List[Dict]:
        """Use AI to verify and re-rank top scheme matches for better accuracy"""
        try:
            # Create concise scheme summaries for AI
            schemes_summary = []
            for s in schemes:
                schemes_summary.append({
                    'id': s['scheme_id'],
                    'name': s['scheme_name'],
                    'type': s['scheme_type'],
                    'eligibility': s['eligibility'],
                    'target': s['target_beneficiaries']
                })
            
            prompt = f"""
User Profile:
- Age: {user_profile.age}
- Occupation: {user_profile.occupation}
- Income: ₹{user_profile.income}
- Location: {user_profile.location_type}
- Gender: {user_profile.gender}
- Family Size: {user_profile.family_size}
- Education: {user_profile.education_level}

Pre-filtered Schemes:
{json.dumps(schemes_summary, indent=2, ensure_ascii=False)}

Verify which schemes this user is ACTUALLY eligible for. Consider:
1. Does occupation truly match scheme target?
2. Are there hidden eligibility criteria?
3. Is this a practical, realistic match?

Respond with ONLY a JSON array of scheme IDs that are truly eligible, ordered by best match first.
Example: [5, 12, 3, 8]
"""
            
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\[[\d,\s]+\]', response_text)
            if json_match:
                verified_ids = json.loads(json_match.group())
                
                # Reorder schemes based on AI verification
                verified_schemes = []
                for scheme_id in verified_ids:
                    scheme = next((s for s in schemes if s['scheme_id'] == scheme_id), None)
                    if scheme:
                        # Boost confidence for AI-verified schemes
                        scheme['confidence'] = min(98, scheme['confidence'] + 5)
                        if 'AI Verified' not in scheme['notes']:
                            scheme['notes'].append('✓ AI Verified')
                        verified_schemes.append(scheme)
                
                # Add remaining schemes with slightly lower confidence
                for scheme in schemes:
                    if scheme['scheme_id'] not in verified_ids:
                        scheme['confidence'] = max(55, scheme['confidence'] - 10)
                        verified_schemes.append(scheme)
                
                return verified_schemes
        except Exception as e:
            print(f"AI verification failed, using rule-based results: {e}")
        
        # Return original if AI fails
        return schemes


class SimplificationAgent(BaseAgent):
    """Agent that simplifies complex scheme information"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key, AgentType.SIMPLIFIER)
    
    def _create_system_prompt(self) -> str:
        return """आप सरकारी योजनाओं को आम लोगों के लिए सरल हिंदी में समझाने वाले विशेषज्ञ हैं।
आपका काम जटिल योजना विवरणों को सरल, समझने में आसान भाषा में समझाना है।

दिशा-निर्देश:
1. सरल हिंदी शब्दों का उपयोग करें जो गांव के लोग और आम लोग समझ सकें
2. कठिन शब्दों और तकनीकी शब्दों से बचें
3. रोजमर्रा के उदाहरण और तुलना का उपयोग करें
4. जटिल प्रक्रियाओं को सरल चरणों में तोड़ें
5. व्यावहारिक लाभों पर ध्यान केंद्रित करें
6. बातचीत के लहजे का उपयोग करें
7. यदि तकनीकी शब्द आवश्यक हैं, तो उन्हें ब्रैकेट में समझाएं

आउटपुट प्रारूप:
- सरल व्याख्या (2-3 वाक्य)
- किसे मिल सकता है (सरल शब्दों में)
- आपको क्या मिलेगा (स्पष्ट लाभ)
- कैसे आवेदन करें (सरल चरण)

सभी जवाब केवल सरल हिंदी में दें। अंग्रेजी का उपयोग न करें।
"""
    
    def process(self, scheme_data: Dict) -> Dict[str, str]:
        """Simplify scheme information"""
        
        prompt = f"""
इस सरकारी योजना की जानकारी को आम लोगों के लिए सरल हिंदी में समझाएं:

योजना: {scheme_data['scheme_name']}
प्रकार: {scheme_data['scheme_type']}
पात्रता: {scheme_data['eligibility']}
लाभ: {scheme_data['benefits']}
आवश्यक दस्तावेज: {', '.join(scheme_data['required_documents'])}
आवेदन कैसे करें: {scheme_data['application_process']}

कृपया सरल हिंदी में व्याख्या दें। निर्देशों में बताए गए प्रारूप का पालन करें।
"""
        
        try:
            response = self.model.generate_content(prompt)
            
            # Parse the response into structured format
            simplified_text = response.text
            
            # Extract sections (simplified parsing)
            sections = {
                'simple_explanation': '',
                'who_can_get': '',
                'benefits_simple': '',
                'how_to_apply_simple': '',
                'full_simplified': simplified_text
            }
            
            # Try to parse sections
            lines = simplified_text.split('\n')
            current_section = 'simple_explanation'
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                lower_line = line.lower()
                if 'who can get' in lower_line or 'eligibility' in lower_line or 'किसे मिल' in lower_line or 'पात्रता' in lower_line:
                    current_section = 'who_can_get'
                elif 'benefit' in lower_line or 'what you' in lower_line or 'लाभ' in lower_line or 'क्या मिल' in lower_line:
                    current_section = 'benefits_simple'
                elif 'how to apply' in lower_line or 'application' in lower_line or 'आवेदन' in lower_line or 'कैसे' in lower_line:
                    current_section = 'how_to_apply_simple'
                else:
                    sections[current_section] += line + ' '
            
            return sections
            
        except Exception as e:
            print(f"Simplification failed: {e}")
            return {
                'simple_explanation': scheme_data['benefits'],
                'who_can_get': scheme_data['eligibility'],
                'benefits_simple': scheme_data['benefits'],
                'how_to_apply_simple': scheme_data['application_process'],
                'full_simplified': f"Error in simplification: {str(e)}"
            }


class ApplicationGuideAgent(BaseAgent):
    """Agent that provides step-by-step application guidance"""
    
    def __init__(self, api_key: str):
        super().__init__(api_key, AgentType.APPLICATION_GUIDE)
    
    def _create_system_prompt(self) -> str:
        return """आप सरकारी योजना आवेदन के लिए विशेषज्ञ मार्गदर्शक हैं।
आपका काम योजनाओं में आवेदन करने के लिए स्पष्ट, चरण-दर-चरण निर्देश प्रदान करना है।

दिशा-निर्देश:
1. प्रक्रिया को क्रमांकित चरणों में विभाजित करें
2. बताएं कि कहां जाना है (ऑनलाइन पोर्टल, कार्यालय, बैंक, आदि)
3. पहले से कौन से दस्तावेज तैयार करने हैं
4. प्रत्येक चरण में क्या उम्मीद करें
5. सामान्य गलतियों से बचने के लिए
6. समय सीमा की अपेक्षाएं
7. यदि उपलब्ध हो तो हेल्पलाइन नंबर
8. सरल हिंदी भाषा का प्रयोग करें

प्रारूप:
स्पष्ट कार्रवाई बिंदुओं के साथ चरण-दर-चरण मार्गदर्शिका

सभी जवाब केवल सरल हिंदी में दें। अंग्रेजी का उपयोग कम से कम करें।
"""
    
    def process(self, scheme_data: Dict, user_profile: Optional[UserProfile] = None) -> Dict[str, Any]:
        """Generate application guide"""
        
        user_context = ""
        if user_profile:
            user_context = f"\nउपयोगकर्ता प्रोफ़ाइल: उम्र {user_profile.age}, {user_profile.location_type}, {user_profile.occupation}"
        
        prompt = f"""
इस योजना के लिए विस्तृत चरण-दर-चरण आवेदन मार्गदर्शिका बनाएं:

योजना: {scheme_data['scheme_name']}
आवेदन कैसे करें: {scheme_data['application_process']}
आवश्यक दस्तावेज: {', '.join(scheme_data['required_documents'])}
कार्यान्वयन एजेंसी: {scheme_data['implementing_agency']}
{user_context}

कृपया प्रदान करें:
1. आवेदन से पहले की जांच सूची
2. विस्तृत चरण-दर-चरण प्रक्रिया
3. आवश्यक दस्तावेज (प्रत्येक क्या है समझाएं)
4. कहां जमा करना है
5. समय सीमा
6. सुझाव और सामान्य गलतियों से बचने के लिए
7. अस्वीकार होने पर क्या करें

सरल हिंदी भाषा का उपयोग करें।
"""
        
        try:
            response = self.model.generate_content(prompt)
            
            return {
                'scheme_name': scheme_data['scheme_name'],
                'guide': response.text,
                'documents_needed': scheme_data['required_documents'],
                'application_method': scheme_data['application_process']
            }
            
        except Exception as e:
            print(f"Guide generation failed: {e}")
            return {
                'scheme_name': scheme_data['scheme_name'],
                'guide': f"Error generating guide: {str(e)}",
                'documents_needed': scheme_data['required_documents'],
                'application_method': scheme_data['application_process']
            }


class QueryResolverAgent(BaseAgent):
    """Agent that answers user questions about schemes"""
    
    def __init__(self, api_key: str, schemes_data: List[Dict]):
        super().__init__(api_key, AgentType.QUERY_RESOLVER)
        self.schemes_data = schemes_data
        # Create a conversation history
        self.chat = self.model.start_chat(history=[])
    
    def _create_system_prompt(self) -> str:
        return """आप भारतीय सरकारी योजनाओं के बारे में सवालों के जवाब देने वाले सहायक हैं।

दिशा-निर्देश:
1. सरल, बातचीत की भाषा में जवाब दें
2. सरल हिंदी का उपयोग करें
3. सटीक और तथ्यात्मक रहें
4. यदि आप नहीं जानते हैं, तो कहें
5. प्रासंगिक होने पर विशिष्ट योजना के नाम प्रदान करें
6. मित्रवत, प्रोत्साहक तरीके से समझाएं
7. उपयोगकर्ताओं को पात्रता समझने में मदद करें
8. अगले चरणों के लिए मार्गदर्शन करें

आपके पास 89+ सरकारी योजनाओं की जानकारी है।

सभी जवाब सरल हिंदी में दें।
"""
    
    def process(self, query: str, context: Optional[Dict] = None) -> str:
        """Answer user query"""
        
        # Add context if provided
        context_text = ""
        if context:
            if 'matched_schemes' in context:
                schemes_list = [s['scheme_name'] for s in context['matched_schemes'][:5]]
                context_text = f"\n\nउपयोगकर्ता की योग्य योजनाएं: {', '.join(schemes_list)}"
            if 'current_scheme' in context:
                context_text += f"\n\nवर्तमान में चर्चा: {context['current_scheme']['scheme_name']}"
        
        prompt = f"""
उपयोगकर्ता का सवाल: {query}
{context_text}

सरल हिंदी में सहायक, सटीक जवाब दें।
"""
        
        try:
            response = self.chat.send_message(prompt)
            return response.text
            
        except Exception as e:
            print(f"Query resolution failed: {e}")
            return f"मुझे अभी इसका जवाब देने में परेशानी हो रही है। Error: {str(e)}"
    
    def reset_conversation(self):
        """Reset the conversation history"""
        self.chat = self.model.start_chat(history=[])


class SchemeFinderOrchestrator:
    """Main orchestrator that coordinates all agents"""
    
    def __init__(self, api_key: str, schemes_json_path: str):
        # Load schemes data
        with open(schemes_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.schemes_data = data['schemes']
        
        # Initialize agents
        self.eligibility_agent = EligibilityMatcherAgent(api_key, self.schemes_data)
        self.simplifier_agent = SimplificationAgent(api_key)
        self.guide_agent = ApplicationGuideAgent(api_key)
        self.query_agent = QueryResolverAgent(api_key, self.schemes_data)
        
        self.current_user_profile = None
        self.matched_schemes = None
    
    def set_user_profile(self, profile: UserProfile):
        """Set the current user profile"""
        self.current_user_profile = profile
        # Find eligible schemes
        self.matched_schemes = self.eligibility_agent.process(profile)
    
    def get_eligible_schemes(self) -> Dict[str, Any]:
        """Get schemes eligible for current user"""
        if not self.matched_schemes:
            return {'error': 'Please set user profile first'}
        return self.matched_schemes
    
    def get_simplified_scheme(self, scheme_id: int) -> Dict[str, str]:
        """Get simplified explanation of a scheme"""
        scheme = next((s for s in self.schemes_data if s['scheme_id'] == scheme_id), None)
        if not scheme:
            return {'error': 'Scheme not found'}
        
        return self.simplifier_agent.process(scheme)
    
    def get_application_guide(self, scheme_id: int) -> Dict[str, Any]:
        """Get application guide for a scheme"""
        scheme = next((s for s in self.schemes_data if s['scheme_id'] == scheme_id), None)
        if not scheme:
            return {'error': 'Scheme not found'}
        
        return self.guide_agent.process(scheme, self.current_user_profile)
    
    def ask_question(self, query: str) -> str:
        """Ask a question about schemes"""
        context = {}
        if self.matched_schemes:
            context['matched_schemes'] = self.matched_schemes['matched_schemes']
        
        return self.query_agent.process(query, context)
    
    def get_scheme_by_id(self, scheme_id: int) -> Optional[Dict]:
        """Get scheme details by ID"""
        return next((s for s in self.schemes_data if s['scheme_id'] == scheme_id), None)
    
    def search_schemes(self, keyword: str) -> List[Dict]:
        """Search schemes by keyword"""
        keyword = keyword.lower()
        results = []
        
        for scheme in self.schemes_data:
            if (keyword in scheme['scheme_name'].lower() or
                keyword in scheme['scheme_type'].lower() or
                keyword in scheme['category'].lower() or
                keyword in scheme['benefits'].lower()):
                results.append(scheme)
        
        return results


# Example usage and demo
def create_sample_user_profile() -> UserProfile:
    """Create a sample user profile for testing"""
    return UserProfile(
        age=35,
        income=150000,  # Annual income in rupees
        location_type="rural",
        occupation="farmer",
        gender="male",
        has_bank_account=True,
        caste_category="General",
        family_size=4,
        owns_house=False,
        land_ownership=2.5,  # acres
        education_level="10th pass",
        has_disability=False,
        additional_info={
            "crops": ["wheat", "rice"],
            "has_ration_card": True
        }
    )


def main():
    """Main demo function"""
    print("=" * 70)
    print("GOVERNMENT SCHEME FINDER - MULTI-AGENT SYSTEM")
    print("=" * 70)
    
    # Get API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("\n⚠️  Please set GEMINI_API_KEY environment variable")
        print("   Get your free API key from: https://makersuite.google.com/app/apikey")
        api_key = input("\nEnter your Gemini API key: ").strip()
    
    if not api_key:
        print("❌ API key required!")
        return
    
    # Path to schemes JSON
    schemes_path = input("\nEnter path to schemes.json file: ").strip()
    if not schemes_path:
        schemes_path = "schemes.json"
    
    try:
        # Initialize orchestrator
        print("\n🔄 Initializing AI agents...")
        orchestrator = SchemeFinderOrchestrator(api_key, schemes_path)
        print("✅ All agents ready!")
        
        # Create sample user
        print("\n👤 Creating sample user profile...")
        user = create_sample_user_profile()
        print(f"   Age: {user.age}, Occupation: {user.occupation}, Location: {user.location_type}")
        
        # Set user profile and find schemes
        print("\n🔍 Finding eligible schemes...")
        orchestrator.set_user_profile(user)
        results = orchestrator.get_eligible_schemes()
        
        print(f"\n✅ Found {results['total_matched']} eligible schemes!")
        print("\nTop 5 Matches:")
        print("-" * 70)
        
        for i, scheme in enumerate(results['matched_schemes'][:5], 1):
            print(f"{i}. {scheme['scheme_name']}")
            print(f"   Type: {scheme['scheme_type']}")
            print(f"   Benefits: {scheme['benefits']}")
            print(f"   Confidence: {scheme['confidence']}%")
            if scheme['notes']:
                print(f"   Notes: {', '.join(scheme['notes'])}")
            print()
        
        # Demonstrate simplification
        if results['matched_schemes']:
            first_scheme_id = results['matched_schemes'][0]['scheme_id']
            print(f"\n📖 Getting simplified explanation for first scheme...")
            simplified = orchestrator.get_simplified_scheme(first_scheme_id)
            print("\n" + "=" * 70)
            print(simplified['full_simplified'])
            print("=" * 70)
            
            # Demonstrate application guide
            print(f"\n📝 Generating application guide...")
            guide = orchestrator.get_application_guide(first_scheme_id)
            print("\n" + "=" * 70)
            print(guide['guide'])
            print("=" * 70)
        
        # Interactive Q&A
        print("\n💬 You can now ask questions about schemes (type 'quit' to exit)")
        print("=" * 70)
        
        while True:
            question = input("\n❓ Your question: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                break
            
            if not question:
                continue
            
            answer = orchestrator.ask_question(question)
            print(f"\n🤖 Answer: {answer}")
        
        print("\n👋 Thank you for using Scheme Finder!")
        
    except FileNotFoundError:
        print(f"❌ Error: Could not find schemes.json at {schemes_path}")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()