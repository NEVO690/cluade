// Translucent water for the chunk water sub-mesh (URP). Gently animated, lit by the sun,
// with a fresnel tint so shallow views look clearer than grazing ones.
Shader "VoxelWorld/VoxelWater"
{
    Properties
    {
        _BlockTextures ("Block Textures", 2DArray) = "" {}
        _ShallowColor ("Shallow Colour", Color) = (0.25, 0.55, 0.85, 0.55)
        _DeepColor ("Grazing Colour", Color) = (0.10, 0.28, 0.55, 0.85)
        _WaveSpeed ("Wave Speed", Range(0, 2)) = 0.35
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma target 3.5
            #pragma require 2darray
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D_ARRAY(_BlockTextures);
            SAMPLER(sampler_BlockTextures);

            CBUFFER_START(UnityPerMaterial)
                half4 _ShallowColor;
                half4 _DeepColor;
                float _WaveSpeed;
            CBUFFER_END

            float4 _VoxelSkyAmbient;
            float4 _VoxelGroundAmbient;

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
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                // Small bob on the surface only (upward-facing vertices).
                float up = step(0.5, input.normalOS.y);
                positionWS.y += up * (sin(_Time.y * 1.7 + positionWS.x * 0.9 + positionWS.z * 0.7) * 0.025 - 0.03);
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.uv = input.uv;
                o.color = input.color;
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 Frag(Varyings input, FRONT_FACE_TYPE cullFace : FRONT_FACE_SEMANTIC) : SV_Target
            {
                float t = _Time.y * _WaveSpeed;
                float2 uvA = input.positionWS.xz * 0.5 + float2(t, t * 0.6);
                float2 uvB = input.positionWS.xz * 0.37 - float2(t * 0.7, t * 0.3);
                bool top = input.normalWS.y > 0.5;
                float2 uv = top ? uvA : input.uv.xy + float2(0, t);
                half3 texA = SAMPLE_TEXTURE2D_ARRAY(_BlockTextures, sampler_BlockTextures, uv, input.uv.z).rgb;
                half3 texB = SAMPLE_TEXTURE2D_ARRAY(_BlockTextures, sampler_BlockTextures, uvB, input.uv.z).rgb;
                half3 tex = top ? (texA + texB) * 0.5h : texA;

                half3 normal = normalize(input.normalWS) * IS_FRONT_VFACE(cullFace, 1.0h, -1.0h);
                float3 viewDir = normalize(GetWorldSpaceViewDir(input.positionWS));
                half fresnel = pow(1.0h - saturate(abs(dot(normal, viewDir))), 3.0h);
                half4 baseColor = lerp(_ShallowColor, _DeepColor, fresnel);

                Light mainLight = GetMainLight(TransformWorldToShadowCoord(input.positionWS));
                half shadow = lerp(0.55h, 1.0h, mainLight.shadowAttenuation);
                half3 ambient = lerp(_VoxelGroundAmbient.rgb, _VoxelSkyAmbient.rgb, 0.8h);
                half ndotl = saturate(dot(normal, mainLight.direction));
                half3 lit = baseColor.rgb * tex * 1.6h * (mainLight.color * (0.35h + 0.65h * ndotl) * shadow + ambient);

                float3 halfDir = normalize(mainLight.direction + viewDir);
                half spec = pow(saturate(dot(normal, halfDir)), 96.0h) * shadow * (top ? 1.0h : 0.0h);
                lit += mainLight.color * spec * 0.6h;

                lit = MixFog(lit, input.fogFactor);
                return half4(lit, saturate(baseColor.a + spec));
            }
            ENDHLSL
        }
    }

    FallBack Off
}
