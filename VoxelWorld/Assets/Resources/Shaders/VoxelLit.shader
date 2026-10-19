// Chunk shader for opaque and alpha-tested blocks (URP).
// Vertex colour: rgb = biome tint x face shade, a = ambient occlusion.
// TEXCOORD0: xy = tile UV, z = texture-array layer (+512 for emissive faces).
Shader "VoxelWorld/VoxelLit"
{
    Properties
    {
        _BlockTextures ("Block Textures", 2DArray) = "" {}
        _Cutoff ("Alpha Cutoff", Range(0, 1)) = 0.5
        _AOStrength ("Ambient Occlusion Strength", Range(0, 1)) = 0.85
        _EmissionStrength ("Emission Strength", Range(0, 4)) = 1.6
    }

    SubShader
    {
        Tags { "RenderType" = "TransparentCutout" "Queue" = "AlphaTest" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        TEXTURE2D_ARRAY(_BlockTextures);
        SAMPLER(sampler_BlockTextures);

        CBUFFER_START(UnityPerMaterial)
            float _Cutoff;
            float _AOStrength;
            float _EmissionStrength;
        CBUFFER_END

        // Set globally by the atmosphere system.
        float4 _VoxelSkyAmbient;
        float4 _VoxelGroundAmbient;

        float DecodeLayer(float raw, out float emissive)
        {
            emissive = step(511.5, raw);
            return raw - emissive * 512.0;
        }

        half SampleAlpha(float3 uv)
        {
            float emissive;
            float layer = DecodeLayer(uv.z, emissive);
            return SAMPLE_TEXTURE2D_ARRAY(_BlockTextures, sampler_BlockTextures, uv.xy, layer).a;
        }
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull Back
            ZWrite On
            ZTest LEqual

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                half4 color : COLOR;
                float3 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 uv : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionWS : TEXCOORD2;
                half4 color : COLOR;
                half fogFactor : TEXCOORD3;
            };

            Varyings Vert(Attributes input)
            {
                Varyings o;
                VertexPositionInputs pos = GetVertexPositionInputs(input.positionOS.xyz);
                o.positionCS = pos.positionCS;
                o.positionWS = pos.positionWS;
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.uv = input.uv;
                o.color = input.color;
                o.fogFactor = ComputeFogFactor(pos.positionCS.z);
                return o;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float emissive;
                float layer = DecodeLayer(input.uv.z, emissive);
                half4 albedo = SAMPLE_TEXTURE2D_ARRAY(_BlockTextures, sampler_BlockTextures, input.uv.xy, layer);
                clip(albedo.a - _Cutoff);

                half3 baseColor = albedo.rgb * input.color.rgb;
                half3 normal = normalize(input.normalWS);
                half ao = lerp(1.0h, input.color.a, (half)_AOStrength);

                float4 shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                Light mainLight = GetMainLight(shadowCoord);
                half ndotl = saturate(dot(normal, mainLight.direction));
                // Wrap lighting keeps faces turned away from the sun readable.
                half wrapped = saturate((ndotl + 0.25h) / 1.25h);
                half3 direct = mainLight.color * (wrapped * mainLight.shadowAttenuation * mainLight.distanceAttenuation);

                half3 ambient = lerp(_VoxelGroundAmbient.rgb, _VoxelSkyAmbient.rgb, normal.y * 0.5h + 0.5h);
                half3 lit = baseColor * (direct + ambient) * ao;
                lit = lerp(lit, albedo.rgb * _EmissionStrength, emissive);

                lit = MixFog(lit, input.fogFactor);
                return half4(lit, 1.0h);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex ShadowVert
            #pragma fragment ShadowFrag
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float3 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 uv : TEXCOORD0;
            };

            Varyings ShadowVert(Attributes input)
            {
                Varyings o;
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);
            #if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
                float3 lightDirection = normalize(_LightPosition - positionWS);
            #else
                float3 lightDirection = _LightDirection;
            #endif
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirection));
            #if UNITY_REVERSED_Z
                positionCS.z = min(positionCS.z, UNITY_NEAR_CLIP_VALUE);
            #else
                positionCS.z = max(positionCS.z, UNITY_NEAR_CLIP_VALUE);
            #endif
                o.positionCS = positionCS;
                o.uv = input.uv;
                return o;
            }

            half4 ShadowFrag(Varyings input) : SV_Target
            {
                clip(SampleAlpha(input.uv) - _Cutoff);
                return 0;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex DepthVert
            #pragma fragment DepthFrag

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 uv : TEXCOORD0;
            };

            Varyings DepthVert(Attributes input)
            {
                Varyings o;
                o.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                o.uv = input.uv;
                return o;
            }

            half DepthFrag(Varyings input) : SV_Target
            {
                clip(SampleAlpha(input.uv) - _Cutoff);
                return input.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex DepthNormalsVert
            #pragma fragment DepthNormalsFrag

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float3 uv : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 uv : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
            };

            Varyings DepthNormalsVert(Attributes input)
            {
                Varyings o;
                o.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.uv = input.uv;
                return o;
            }

            half4 DepthNormalsFrag(Varyings input) : SV_Target
            {
                clip(SampleAlpha(input.uv) - _Cutoff);
                return half4(NormalizeNormalPerPixel(input.normalWS), 0.0);
            }
            ENDHLSL
        }
    }

    FallBack "Hidden/Universal Render Pipeline/FallbackError"
}
